import json
from tqdm import tqdm
from pathlib import Path
import pandas as pd
from functools import partial
import argparse
import os

# Prepare TAT dataset in such format (https://github.com/voidful/asr-training):
"""
path,text
/xxx/2.wav,被你拒絕而記仇
/xxx/4.wav,電影界的人
/xxx/7.wav,其實我最近在想
"""

TAILO = "台羅"
TAILONUM = "台羅數字調"
TAIWEN = "漢羅台文"


CLEAN_MAPPING = {
    TAILONUM:
        {
            "﹖": "?",
            "！": "!",
            "％": "%",
            "（": "(",
            "）": ")",
            "，": ",",
            "：": ":",
            "；": ";",
            "？": "?",
            "—": "--",
            "─": "-",
        },
    TAIWEN:
        {
            "﹖": "？",
            "?": "？",
            "!": "！",
            "(": "（",
            ")": "）",
            ",": "，",
            ":": "：",
            ";": "；",
        }
}

ACCEPTABLE_CHARS = (
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "àáéìîòúāō"
    " "
    '!"%()+,-./:;=?_~'
    "‘’“”'"
    "…⋯"
    "、。『』"
    "－"
)


def get_wav_from_txt(txt_path, wav_dir):
    f_name = txt_path.stem
    spk_name = txt_path.parent.name
    pattern = f"{f_name}-[0-9]*.wav"
    [wav_path] = (wav_dir / spk_name).glob(pattern)
    return wav_path


def get_transcription_from_json(json_path, transcript_type):
    with open(json_path) as f:
        json_data = json.load(f)
        txt = json_data[transcript_type]
        txt = clean_text(txt, transcript_type)
        return txt


def clean_text(txt, transcript_type):
    if transcript_type == TAILONUM: #"台羅數字調"
        txt = txt.strip()
        txt = txt.replace("'", " ")
        txt = txt.replace('"', " ")
        txt = txt.replace("“", " ")
        txt = txt.replace("”", " ")
        txt = txt.replace(":", " ")
        txt = txt.replace(")", " ")
        txt = txt.replace("(", " ")
        txt = txt.strip()
        if txt.endswith(","):
            txt = txt[:-1] + "."
        if txt[-1] not in "?!.":
            txt += "."
        return txt
    elif transcript_type == TAIWEN: #"漢羅台文"
        if txt.endswith("，"):
            txt = txt[:-1] + "。"
        if txt[-1] not in "？。！":
            txt += "。"
        return txt
    else:
        raise NotImplementedError


def validate_transcription(transcript, transcript_type, bad_count, tokenizer=None, verbose_fp=None):
    cleaned_transcript = transcript
    if transcript_type == TAILONUM: #"台羅數字調"
        for bad_char, good_char in CLEAN_MAPPING[transcript_type].items():
            cleaned_transcript = cleaned_transcript.replace(bad_char, good_char)
        for c in cleaned_transcript:
            if c not in ACCEPTABLE_CHARS:
                print(f"{bad_count + 1}\t{c}\t: {cleaned_transcript}", file=verbose_fp)
                return None, bad_count + 1
        return cleaned_transcript, bad_count
    elif transcript_type == TAIWEN: #"漢羅台文"
        for bad_char, good_char in CLEAN_MAPPING[transcript_type].items():
            cleaned_transcript = cleaned_transcript.replace(bad_char, good_char)
        
        # Check by tokenizer
        decoded_str = tokenizer.decode(tokenizer(cleaned_transcript)["input_ids"], skip_special_tokens=True)
        
        if cleaned_transcript != decoded_str:
            print(f"{bad_count + 1}\t {cleaned_transcript}", file=verbose_fp)
            return None, bad_count + 1
        
        return cleaned_transcript, bad_count
    else:
        raise NotImplementedError
        return cleaned_transcript, -1


def main(args):
    tokenizer = None
    ############
    #  Config  #
    ############
    # args
    if args.transcript_type == "tailo":
        transcript_type = TAILO #"台羅"
    elif args.transcript_type == "taiwen":
        transcript_type = TAIWEN #"漢羅台文"
        from transformers import WhisperTokenizer
        tokenizer = WhisperTokenizer.from_pretrained("openai/whisper-medium", task="transcribe", language="chinese")
    elif args.transcript_type == "tailonum":
        transcript_type = TAILONUM #台羅數字調
    else:
        raise NotImplementedError
    print(f"Transcript Type: {transcript_type}")

    wav_type = "condenser"
    TAT_root = args.TAT_root
    output_root = args.output_root

    # paths
    TAT_root = Path(TAT_root).resolve()
    output_root = Path(output_root).resolve()
    os.makedirs(output_root, exist_ok=True)
    output_path = output_root / f"{TAT_root.name}.csv"

    TAT_txt_dir = TAT_root / "json"
    TAT_wav_dir = TAT_root / wav_type / "wav"

    # data list
    TAT_txt_list = list(TAT_txt_dir.rglob("*.json"))
    TAT_wav_list = [get_wav_from_txt(txt_path, TAT_wav_dir) for txt_path in tqdm(TAT_txt_list)]

    assert len(TAT_txt_list) == len(TAT_wav_list)

    tqdm.pandas()
    TAT_df = pd.DataFrame(
        {
            "json_path": TAT_txt_list,
            "wav_path": TAT_wav_list,
        }
    )
    get_transcript = partial(get_transcription_from_json, transcript_type=transcript_type)
    TAT_df["transcription"] = TAT_df["json_path"].map(get_transcript)

    bad_count = 0
    output_buffer = []
    for idx, data in TAT_df[["wav_path", "transcription"]].iterrows():
        wav_path = data["wav_path"]
        transcript = data["transcription"]
        result, bad_count = validate_transcription(transcript, transcript_type, bad_count, tokenizer)
        if result is not None:
            output_buffer.append(
                [
                    wav_path,
                    result,
                ]
            )

    pd.DataFrame(output_buffer).to_csv(output_path, index=None, header=["path", "text"])
    print("Output at", output_path)


if __name__ == "__main__":
    """
    e.g.
    python prepare_TAT.py --TAT_root /storage/speech_dataset/TAT/TAT-Vol1-train
    python prepare_TAT.py --TAT_root /storage/speech_dataset/TAT/TAT-Vol1-eval
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--TAT_root", type=str, default="/storage/speech_dataset/TAT/TAT-Vol1-train")
    parser.add_argument("--output_root", type=str, default="../TAT-data")
    parser.add_argument("--transcript_type", type=str, default="tailonum")
    args = parser.parse_args()
    main(args)
