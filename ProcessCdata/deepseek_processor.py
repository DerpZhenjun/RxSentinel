"""DeepSeek 云端 JSON Mode 推理入口：OpenAI 兼容客户端指向官方 Base URL。

CLI 与 pipeline_runner 共用 `ai_processor_common.run_platform_pipeline`。"""

import sys
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

import json
import logging
import os
from dataclasses import dataclass
from openai import OpenAI

logger = logging.getLogger(__name__)

from ai_processor_common import (
    DEFAULT_AI_PROMPT_BODY,
    compose_prompt_template,
    load_prompt_template,
    load_input_lines,
    run_platform_pipeline,
)

@dataclass
class DeepSeekConfig:
    base_dir: str
    model_name: str
    client: OpenAI
    prompt_template: str
    max_process_count: int | None = None
    read_source: str = "local"
    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_db_name: str = "Oestrogen"


# CLI 直连时的默认平台表、模型名等（WebUI 路径走 `DeepSeekConfig` 显式注入）。
PLATFORMS = ["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"]
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_BASE_DIR = os.path.join(CURRENT_DIR, "data")
_DEFAULT_MODEL = "deepseek-chat"


def process_platform(platform: str, cfg: DeepSeekConfig) -> None:
    """单平台批跑：输入来自 `load_input_lines`，输出 JSONL + 日志 + 可选图表。"""
    input_file = os.path.join(cfg.base_dir, platform, "jsonl", "filtered_comments.jsonl")
    output_file = os.path.join(cfg.base_dir, platform, "jsonl", "ai_extracted_channels.jsonl")
    chart_output_file = os.path.join(cfg.base_dir, platform, "jsonl", "ai_analysis_report.png")
    log_file = os.path.join(cfg.base_dir, platform, "jsonl", "ai_extract_log.txt")

    logger.info("[%s] 开始 DeepSeek 处理 | 模型: %s", platform.upper(), cfg.model_name)

    try:
        lines = load_input_lines(
            platform, input_file,
            cfg.read_source, cfg.mongo_uri, cfg.mongo_db_name,
            cfg.max_process_count,
        )
        if lines is None:
            return
    except Exception as e:
        logger.error("[%s] 读取输入数据出错: %s", platform.upper(), e, exc_info=True)
        return

    def call_deepseek(formatted_prompt: str) -> dict:
        response = cfg.client.chat.completions.create(
            model=cfg.model_name,
            messages=[
                {"role": "system", "content": "你必须且只能输出合法的 JSON 格式。"},
                {"role": "user", "content": formatted_prompt},
            ],
            response_format={"type": "json_object"},
            stream=False,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        # 偶发 markdown 围栏：剥壳后再 `json.loads`。
        if raw.startswith("```json"):
            raw = raw[7:-3].strip()
        elif raw.startswith("```"):
            raw = raw[3:-3].strip()
        return json.loads(raw)

    run_platform_pipeline(
        platform=platform,
        input_lines=lines,
        output_file=output_file,
        chart_output_file=chart_output_file,
        log_file=log_file,
        prompt_template=cfg.prompt_template,
        engine="DeepSeek",
        model_name=cfg.model_name,
        call_llm=call_deepseek,
    )


def run_ai_pipeline(model_name, max_count, platforms, base_dir, api_key,
                    read_source="local", mongo_uri=None, mongo_db=None,
                    custom_prompt=None):
    """组装 `DeepSeekConfig` 逐平台跑；不落模块级可变全局。"""
    if not api_key or not api_key.strip():
        raise ValueError("缺少 DeepSeek API Key！请在网页界面中填写。")

    prompt_template = (
        compose_prompt_template(custom_prompt)
        if isinstance(custom_prompt, str) and custom_prompt.strip()
        else load_prompt_template(DEFAULT_AI_PROMPT_BODY)
    )
    cfg = DeepSeekConfig(
        base_dir=os.path.join(base_dir, "ProcessCdata", "data"),
        model_name=model_name,
        client=OpenAI(api_key=api_key.strip(), base_url="https://api.deepseek.com"),
        prompt_template=prompt_template,
        max_process_count=max_count if max_count > 0 else None,
        read_source=read_source,
        mongo_uri=mongo_uri or "mongodb://127.0.0.1:27017",
        mongo_db_name=mongo_db or "Oestrogen",
    )
    for plat in platforms:
        process_platform(plat, cfg)

    return "✅ DeepSeek API 提取任务完成！请前往界面或输出目录查看分析图表。"


if __name__ == "__main__":
    import argparse as _ap

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _p = _ap.ArgumentParser(description="DeepSeek 多平台 AI 分析流水线（供 WebUI 以子进程方式调用）")
    _p.add_argument("--root-dir",    required=True,                        help="项目根目录")
    _p.add_argument("--platforms",   nargs="+", required=True,             help="要处理的平台列表")
    _p.add_argument("--model",       default=_DEFAULT_MODEL,               help="DeepSeek 模型名称")
    _p.add_argument("--max-count",   type=int, default=0,                  help="分析条数上限，0 为全量")
    _p.add_argument("--api-key",     required=True,                        help="DeepSeek 密钥（sk-…）")
    _p.add_argument("--read-source", default="local", choices=["local", "db"])
    _p.add_argument("--mongo-uri",   default="mongodb://127.0.0.1:27017")
    _p.add_argument("--mongo-db",    default="Oestrogen")
    _args = _p.parse_args()

    logger.info("启动 DeepSeek 多平台批处理系统 | 模型: %s | 平台: %s", _args.model, _args.platforms)
    result = run_ai_pipeline(
        model_name=_args.model,
        max_count=_args.max_count,
        platforms=_args.platforms,
        base_dir=_args.root_dir,
        api_key=_args.api_key,
        read_source=_args.read_source,
        mongo_uri=_args.mongo_uri,
        mongo_db=_args.mongo_db,
        custom_prompt=None,  # `None` → `load_prompt_template` 读配置档
    )
    print(result)
    logger.info("所有平台的 DeepSeek 挖掘任务执行完毕")
