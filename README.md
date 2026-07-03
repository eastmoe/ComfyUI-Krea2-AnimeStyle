# Comfy-Krea2-AnimeStyle

ComfyUI custom node for grouped anime illustration style prompt injection.

The node appears under:

```text
eastmoe -> Comfy-Krea2-AnimeStyle
```

## Node

### Krea2 Anime Style CLIP Text Encode

Inputs:

- `clip`: the CLIP/text encoder used for final conditioning.
- `positive_text`: user positive prompt.
- `lora_trigger_text`: LoRA trigger words prefixed directly to the final positive prompt, without translation or refinement.
- `negative_text`: user negative prompt.
- `style_selection`: saved selected style IDs. In the ComfyUI frontend this is rendered as grouped checkboxes.
- `translate_prompts`: when enabled, translates the user prompts to English through the connected CLIP-LLM before encoding.
- `translation_max_length`: max CLIP-LLM generation length, capped at `1024`.
- `refine_prompt`: when enabled, expands and polishes the positive prompt through the connected CLIP-LLM before appending styles.
- `refinement_max_length`: max CLIP-LLM generation length for positive prompt refinement, capped at `1024`.

Outputs:

- `positive`: positive conditioning with selected style English descriptions appended.
- `negative`: negative conditioning.

### Krea2 Anime Style Prompt Text

Same prompt processing and style selector, but it returns strings instead of encoded conditioning.
The `clip` input is optional and is only required when `translate_prompts` or `refine_prompt` is enabled.
This is intended for subgraphs or any workflow that wants to pass the processed prompt text into another node.

Outputs:

- `positive_text`: positive prompt string with selected style English descriptions appended.
- `negative_text`: negative prompt string after optional translation.

Style data is generated from `C:\Users\StarMoon\Downloads\anime_illustration_glossary.html` into `data/styles.json`.
