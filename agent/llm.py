"""LLM 客户端初始化 — 统一的 ChatModel 工厂

本模块从 .env 文件读取配置，创建兼容 OpenAI 协议的 ChatModel 实例。
因为 Moonshot（Kimi）API 完全兼容 OpenAI 协议，所以直接使用
langchain_openai.ChatOpenAI 即可对接。

使用方式:
    from agent.llm import get_chat_model
    llm = get_chat_model()
"""

import os
import logging

# dotenv 负责将 .env 文件中的变量加载到 os.environ
from dotenv import load_dotenv

# 使用 LangChain 最新的 init_chat_model 进行统一的大模型初始化
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

# 在模块级别加载 .env，确保后续读取环境变量时已就绪
load_dotenv()


def get_chat_model() -> BaseChatModel:
    """创建并返回配置好的 ChatOpenAI 实例

    功能:
        从环境变量读取 API Key、Base URL、模型名称和温度参数，
        构建一个可直接用于 LangChain Agent 的 Chat 模型。

    返回:
        BaseChatModel - 已配置好的 LLM 客户端实例

    引发:
        ValueError - 如果必需的环境变量未设置
    """
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_API_BASE")
    model_name = os.getenv("LLM_MODEL", "kimi-k2-0711-preview")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.1"))

    # 校验必需参数
    if not api_key:
        raise ValueError(
            "环境变量 OPENAI_API_KEY 未设置，请在 .env 文件中配置"
        )
    if not base_url:
        raise ValueError(
            "环境变量 OPENAI_API_BASE 未设置，请在 .env 文件中配置"
        )

    logger.info(
        "初始化 LLM: model=%s, base_url=%s, temperature=%s",
        model_name, base_url, temperature,
    )

    # 使用 init_chat_model 进行统一的初始化
    # init_chat_model 提供了一种优雅的基于 provider 的实例化方式
    return init_chat_model(
        model=model_name,
        model_provider="openai",  # Moonshot 兼容 openai 协议
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )
