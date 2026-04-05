"""文字转语音技能：腾讯云 TTS（温柔小柠 603004），生成音频并发送到飞书"""
import os
import time
import hmac
import hashlib
import base64
import json
import logging
import httpx

ENABLED = True

TOOL_DEF = {
    "name": "tts_reply",
    "description": "将文字转换为语音并以音频消息发送，当用户要求语音回复时使用",
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "要转换为语音的文字内容"},
        },
        "required": ["text"]
    }
}

_SECRET_ID = os.environ.get("TENCENT_SECRET_ID", "")
_SECRET_KEY = os.environ.get("TENCENT_SECRET_KEY", "")
_VOICE_TYPE = 603004  # 温柔小柠
_MAX_LENGTH = int(os.environ.get("TTS_MAX_LENGTH", "150"))


def _tencent_tts(text: str) -> bytes:
    host = "tts.tencentcloudapi.com"
    action = "TextToVoice"
    timestamp = int(time.time())
    date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))
    payload = json.dumps({"Text": text[:_MAX_LENGTH], "SessionId": str(timestamp), "VoiceType": _VOICE_TYPE})

    canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{host}\nx-tc-action:{action.lower()}\n"
    hashed_payload = hashlib.sha256(payload.encode()).hexdigest()
    canonical_request = f"POST\n/\n\n{canonical_headers}\ncontent-type;host;x-tc-action\n{hashed_payload}"

    credential_scope = f"{date}/tts/tc3_request"
    string_to_sign = f"TC3-HMAC-SHA256\n{timestamp}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}"

    secret_date = hmac.new(f"TC3{_SECRET_KEY}".encode(), date.encode(), hashlib.sha256).digest()
    secret_service = hmac.new(secret_date, b"tts", hashlib.sha256).digest()
    secret_signing = hmac.new(secret_service, b"tc3_request", hashlib.sha256).digest()
    signature = hmac.new(secret_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

    authorization = f"TC3-HMAC-SHA256 Credential={_SECRET_ID}/{credential_scope}, SignedHeaders=content-type;host;x-tc-action, Signature={signature}"

    resp = httpx.post(
        f"https://{host}",
        headers={
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": "2019-08-23",
            "X-TC-Region": "ap-guangzhou",
        },
        content=payload,
        timeout=30,
    )
    data = resp.json()
    if "Response" not in data or "Audio" not in data["Response"]:
        error = data.get("Response", {}).get("Error", {}).get("Message", str(data))
        raise Exception(f"TTS 失败: {error}")
    return base64.b64decode(data["Response"]["Audio"])


async def execute(text: str, chat_id: str, feishu_client, ai_client) -> str:
    if not _SECRET_ID or not _SECRET_KEY:
        return "未配置腾讯云密钥（TENCENT_SECRET_ID / TENCENT_SECRET_KEY）"
    logging.info(f"[TTS] {text[:100]}")
    audio_data = _tencent_tts(text)
    await feishu_client.send_audio(chat_id, audio_data)
    return f"已发送语音消息（{len(text)} 字）"
