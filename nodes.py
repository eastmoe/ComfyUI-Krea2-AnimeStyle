from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CATEGORY = "eastmoe/Comfy-Krea2-AnimeStyle"
STYLE_DATA_PATH = ROOT / "data" / "styles.json"
TRANSLATION_INPUT_LIMIT = 1024
REFINEMENT_INPUT_LIMIT = 1024

REFINE_SYSTEM_PROMPT = """You are an expert prompt engineer for text-to-image models. Your task is to expand the user's prompt into a highly effective image-generation prompt.

Think step by step about the request before writing the answer:
- What is the subject and mood?
- What visual styles, mediums, and lighting options would fit? Consider two or three alternatives and pick the one that best serves the caption.
- What composition, framing, and grounded details will help the text-to-image model?

Then output a single expanded prompt paragraph.

Follow these rules strictly:
1. **Faithfulness First:** Preserve all original subjects, actions, colors, and spatial relationships. Do not add new objects, props, characters, or animals unless the user clearly implies them.
2. **Practical T2I Structure:** Write a prompt that a text-to-image model can parse cleanly. Group subjects with their own attributes and actions. Use grounded phrasing for poses, interactions, and spatial layout.
3. **Style Planning Stays Internal:** Use your internal reasoning to choose style, medium, framing, and lighting. Do not emit planning tags or wrappers in the visible answer body.
4. **Text Rendering:** If the user requests visible text, quotes, labels, or typography, specify the exact text clearly and wrap requested words in quotes.
5. **Avoid Over-Specification:** Do not invent highly specific clothing, colors, materials, or scene details unless the input supports them.
6. **Structure:** Write one cohesive paragraph after the thinking block. No bullets, JSON, or markdown.
7. **Respect Existing Detail:** If the user's prompt is already detailed, lightly polish and finalize rather than heavily expanding -- preserve their phrasing and direction.

8. **Preserve User Medium:** When the user explicitly requests a medium (e.g. "photo of", "photograph of", "illustration of", "painting of", "sketch of", "3D render of"), honor it. Do not pivot to a different medium to avoid difficulty -- match the user's stated intent.

User's Input:
"""


def _load_style_data() -> dict[str, Any]:
    with STYLE_DATA_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


STYLE_DATA = _load_style_data()
STYLE_ITEMS = STYLE_DATA["styles"]
STYLE_BY_ID = {item["id"]: item for item in STYLE_ITEMS}


def _style_aliases(item: dict[str, Any]) -> set[str]:
    values = {
        item.get("id", ""),
        item.get("zh", ""),
        item.get("ja", ""),
        item.get("romaji", ""),
    }
    values.update(part.strip() for part in item.get("zh", "").split("/") if part.strip())
    return {value.lower() for value in values if value}


STYLE_ALIAS_TO_ID: dict[str, str] = {}
for _item in STYLE_ITEMS:
    for _alias in _style_aliases(_item):
        STYLE_ALIAS_TO_ID.setdefault(_alias, _item["id"])


def _clean_lines(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[\n,;，；]+", value or "") if part.strip()]


def _selected_style_items(style_selection: str) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in _clean_lines(style_selection):
        style_id = STYLE_ALIAS_TO_ID.get(raw.lower())
        if style_id is None or style_id in seen:
            continue
        seen.add(style_id)
        selected.append(STYLE_BY_ID[style_id])
    return selected


def _join_prompt(parts: list[str]) -> str:
    return ", ".join(part.strip(" ,\n\t") for part in parts if part and part.strip(" ,\n\t"))


def _strip_translation_output(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^```(?:[a-zA-Z]+)?\s*", "", value)
    value = re.sub(r"\s*```$", "", value)
    value = re.sub(r"^(translation|english|output)\s*:\s*", "", value, flags=re.IGNORECASE)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def _clip_tokenize_for_generation(clip, prompt: str):
    try:
        return clip.tokenize(prompt, skip_template=False, min_length=1, thinking=False)
    except TypeError:
        return clip.tokenize(prompt)


def _clip_generate_text(clip, prompt: str, max_length: int) -> str:
    if not hasattr(clip, "generate") or not hasattr(clip, "decode"):
        raise RuntimeError(
            "A CLIP-LLM feature is enabled, but the connected CLIP does not expose "
            "generate/decode methods. Use a text-generation capable CLIP model, "
            "or turn translate_prompts/refine_prompt off."
        )

    tokens = _clip_tokenize_for_generation(clip, prompt)
    generated_ids = clip.generate(
        tokens,
        do_sample=False,
        max_length=max(1, min(int(max_length), TRANSLATION_INPUT_LIMIT)),
        temperature=1.0,
        top_k=0,
        top_p=1.0,
        min_p=0.0,
        repetition_penalty=1.0,
        presence_penalty=0.0,
    )
    return _strip_translation_output(clip.decode(generated_ids))


def _translate_prompt(clip, text: str, max_length: int, label: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    source = text[:TRANSLATION_INPUT_LIMIT]
    prompt = (
        "Translate the following image-generation prompt into concise natural English.\n"
        "Keep names, artist-neutral style terms, weights such as (word:1.2), LoRA tags, "
        "quality tags, punctuation, and comma-separated prompt structure when useful.\n"
        "Return only the translated prompt, with no notes.\n\n"
        f"{label} prompt:\n{source}"
    )
    return _clip_generate_text(clip, prompt, max_length) or source


def _refine_prompt(clip, text: str, max_length: int) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    source = text[:REFINEMENT_INPUT_LIMIT]
    prompt = f"{REFINE_SYSTEM_PROMPT}\n{source}"
    return _clip_generate_text(clip, prompt, max_length) or source


def _encode_conditioning(clip, text: str):
    if clip is None:
        raise RuntimeError(
            "ERROR: clip input is invalid: None\n\n"
            "If the clip is from a checkpoint loader node your checkpoint does not contain a valid clip or text encoder model."
        )
    tokens = clip.tokenize(text or "")
    if hasattr(clip, "encode_from_tokens_scheduled"):
        return clip.encode_from_tokens_scheduled(tokens)
    return clip.encode_from_tokens(tokens)


def _process_prompt_texts(
    clip,
    positive_text: str,
    negative_text: str,
    style_selection: str,
    translate_prompts: bool,
    translation_max_length: int,
    refine_prompt: bool,
    refinement_max_length: int,
) -> tuple[str, str]:
    positive = positive_text or ""
    negative = negative_text or ""

    if translate_prompts or refine_prompt:
        if clip is None:
            raise RuntimeError("A CLIP-LLM input is required when translate_prompts or refine_prompt is enabled.")

    if translate_prompts:
        positive = _translate_prompt(clip, positive, translation_max_length, "Positive")
        negative = _translate_prompt(clip, negative, translation_max_length, "Negative")

    if refine_prompt:
        positive = _refine_prompt(clip, positive, refinement_max_length)

    style_prompts = [item["prompt_en"] for item in _selected_style_items(style_selection)]
    return _join_prompt([positive, *style_prompts]), negative


class Krea2AnimeStyleCLIPTextEncode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip": ("CLIP", {"tooltip": "CLIP/text encoder used for final conditioning. CLIP-LLM generation is also used when translation is enabled."}),
                "positive_text": (
                    "STRING",
                    {
                        "multiline": True,
                        "dynamicPrompts": True,
                        "default": "",
                        "tooltip": "Positive image prompt written by the user.",
                    },
                ),
                "lora_trigger_text": (
                    "STRING",
                    {
                        "multiline": True,
                        "dynamicPrompts": True,
                        "default": "",
                        "tooltip": "LoRA trigger words prefixed directly to the final positive prompt. This text is not translated or refined.",
                    },
                ),
                "negative_text": (
                    "STRING",
                    {
                        "multiline": True,
                        "dynamicPrompts": True,
                        "default": "",
                        "tooltip": "Negative image prompt written by the user.",
                    },
                ),
                "style_selection": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "krea2AnimeStyleSelector": True,
                        "tooltip": "Selected style IDs. The web UI renders this as grouped checkboxes; manual comma/newline entries also work.",
                    },
                ),
                "translate_prompts": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Translate user positive/negative prompts to English through the connected CLIP-LLM before encoding.",
                    },
                ),
                "translation_max_length": (
                    "INT",
                    {
                        "default": 1024,
                        "min": 1,
                        "max": 1024,
                        "step": 1,
                        "tooltip": "Maximum CLIP-LLM generation length for each translation request.",
                    },
                ),
                "refine_prompt": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Expand and polish the positive prompt with the connected CLIP-LLM before appending selected styles.",
                    },
                ),
                "refinement_max_length": (
                    "INT",
                    {
                        "default": 1024,
                        "min": 1,
                        "max": 1024,
                        "step": 1,
                        "tooltip": "Maximum CLIP-LLM generation length for the positive prompt refinement request.",
                    },
                ),
            }
        }

    RETURN_TYPES = ("CONDITIONING", "CONDITIONING")
    RETURN_NAMES = ("positive", "negative")
    OUTPUT_TOOLTIPS = (
        "Positive conditioning with selected anime style descriptions appended.",
        "Negative conditioning encoded from the user negative prompt.",
    )
    FUNCTION = "encode"
    CATEGORY = CATEGORY
    DESCRIPTION = "Encodes positive and negative prompts, appending checked anime illustration style descriptions to the positive prompt."
    SEARCH_ALIASES = ["anime style", "krea2", "prompt style", "clip llm translate"]

    def encode(
        self,
        clip,
        positive_text: str,
        lora_trigger_text: str,
        negative_text: str,
        style_selection: str,
        translate_prompts: bool,
        translation_max_length: int,
        refine_prompt: bool,
        refinement_max_length: int,
    ):
        positive_with_styles, negative = _process_prompt_texts(
            clip,
            positive_text,
            negative_text,
            style_selection,
            translate_prompts,
            translation_max_length,
            refine_prompt,
            refinement_max_length,
        )
        positive_with_triggers = _join_prompt([lora_trigger_text, positive_with_styles])
        return (
            _encode_conditioning(clip, positive_with_triggers),
            _encode_conditioning(clip, negative),
        )


class Krea2AnimeStylePromptText:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "positive_text": (
                    "STRING",
                    {
                        "multiline": True,
                        "dynamicPrompts": True,
                        "default": "",
                        "tooltip": "Positive image prompt written by the user.",
                    },
                ),
                "negative_text": (
                    "STRING",
                    {
                        "multiline": True,
                        "dynamicPrompts": True,
                        "default": "",
                        "tooltip": "Negative image prompt written by the user.",
                    },
                ),
                "style_selection": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "krea2AnimeStyleSelector": True,
                        "tooltip": "Selected style IDs. The web UI renders this as grouped checkboxes; manual comma/newline entries also work.",
                    },
                ),
                "translate_prompts": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Translate user positive/negative prompts to English through the optional CLIP-LLM before output.",
                    },
                ),
                "translation_max_length": (
                    "INT",
                    {
                        "default": 1024,
                        "min": 1,
                        "max": 1024,
                        "step": 1,
                        "tooltip": "Maximum CLIP-LLM generation length for each translation request.",
                    },
                ),
                "refine_prompt": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Expand and polish the positive prompt with the optional CLIP-LLM before appending selected styles.",
                    },
                ),
                "refinement_max_length": (
                    "INT",
                    {
                        "default": 1024,
                        "min": 1,
                        "max": 1024,
                        "step": 1,
                        "tooltip": "Maximum CLIP-LLM generation length for the positive prompt refinement request.",
                    },
                ),
            },
            "optional": {
                "clip": (
                    "CLIP",
                    {
                        "tooltip": "Optional CLIP-LLM used only when translate_prompts is enabled.",
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("positive_text", "negative_text")
    OUTPUT_TOOLTIPS = (
        "Positive prompt string with selected anime style descriptions appended.",
        "Negative prompt string after optional translation.",
    )
    FUNCTION = "process"
    CATEGORY = CATEGORY
    DESCRIPTION = "Builds positive and negative prompt strings with the same anime style selector, without encoding them."
    SEARCH_ALIASES = ["anime style", "krea2", "prompt string", "subgraph prompt"]

    def process(
        self,
        positive_text: str,
        negative_text: str,
        style_selection: str,
        translate_prompts: bool,
        translation_max_length: int,
        refine_prompt: bool,
        refinement_max_length: int,
        clip=None,
    ):
        return _process_prompt_texts(
            clip,
            positive_text,
            negative_text,
            style_selection,
            translate_prompts,
            translation_max_length,
            refine_prompt,
            refinement_max_length,
        )


NODE_CLASS_MAPPINGS = {
    "Krea2AnimeStyleCLIPTextEncode": Krea2AnimeStyleCLIPTextEncode,
    "Krea2AnimeStylePromptText": Krea2AnimeStylePromptText,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Krea2AnimeStyleCLIPTextEncode": "Krea2 Anime Style CLIP Text Encode",
    "Krea2AnimeStylePromptText": "Krea2 Anime Style Prompt Text",
}
