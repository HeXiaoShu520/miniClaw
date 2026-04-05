"""
配置管理模块
负责加载和管理应用配置，支持从 .env 或 config.toml 读取
"""
import os
import tomli
from pathlib import Path
from pydantic import BaseModel


class FeishuConfig(BaseModel):
    """飞书应用配置"""
    app_id: str
    app_secret: str


class ClaudeConfig(BaseModel):
    """Claude API 配置"""
    api_key: str
    model: str = "claude-sonnet-4-6"
    base_url: str | None = None


class OpenAIConfig(BaseModel):
    """OpenAI API 配置"""
    api_key: str
    model: str = "gpt-4o"
    base_url: str | None = None


class AppConfig(BaseModel):
    """应用主配置"""
    log_level: str = "info"
    log_retention: int = 7
    session_retention: int = 7
    resource_retention: int = 7
    use_topic_reply: bool = True
    use_stream: bool = True
    max_history_turns: int = 10
    system_prompt: str | None = None
    ai_provider: str = "anthropic"  # "anthropic" 或 "openai"
    feishu: FeishuConfig
    claude: ClaudeConfig | None = None
    openai: OpenAIConfig | None = None

    @classmethod
    def load_from_env(cls, path: str | Path) -> "AppConfig":
        """从 .env 文件加载配置"""
        print(f"[Config] 正在加载配置文件: {path}")
        env_vars = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    key, _, value = line.partition("=")
                    k, v = key.strip(), value.strip().strip('"').strip("'")
                    env_vars[k] = v
                    os.environ.setdefault(k, v)

        return cls(
            log_level=env_vars.get("LOG_LEVEL", "info"),
            log_retention=int(env_vars.get("LOG_RETENTION", "7")),
            session_retention=int(env_vars.get("SESSION_RETENTION", "7")),
            resource_retention=int(env_vars.get("RESOURCE_RETENTION", "7")),
            use_topic_reply=env_vars.get("USE_TOPIC_REPLY", "true").lower() == "true",
            use_stream=env_vars.get("USE_STREAM", "true").lower() == "true",
            max_history_turns=int(env_vars.get("MAX_HISTORY_TURNS", "10")),
            system_prompt=env_vars.get("SYSTEM_PROMPT"),
            ai_provider=env_vars.get("AI_PROVIDER", "anthropic").lower(),
            feishu=FeishuConfig(
                app_id=env_vars["FEISHU_APP_ID"],
                app_secret=env_vars["FEISHU_APP_SECRET"]
            ),
            claude=ClaudeConfig(
                api_key=env_vars["CLAUDE_API_KEY"],
                model=env_vars.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
                base_url=env_vars.get("CLAUDE_BASE_URL")
            ) if env_vars.get("CLAUDE_API_KEY") else None,
            openai=OpenAIConfig(
                api_key=env_vars["OPENAI_API_KEY"],
                model=env_vars.get("OPENAI_MODEL", "gpt-4o"),
                base_url=env_vars.get("OPENAI_BASE_URL")
            ) if env_vars.get("OPENAI_API_KEY") else None
        )

    @classmethod
    def load(cls, path: str | Path) -> "AppConfig":
        """从指定路径加载配置文件"""
        print(f"[Config] 正在加载配置文件: {path}")
        with open(path, "rb") as f:
            data = tomli.load(f)
        return cls(**data)

    @classmethod
    def discover(cls) -> "AppConfig":
        """自动发现并加载配置文件，优先 .env，其次 config.toml"""
        # 1. 环境变量指定
        if config_path := os.getenv("ACP_LINK_CONFIG"):
            if config_path.endswith(".env"):
                return cls.load_from_env(config_path)
            return cls.load(config_path)

        # 2. 当前目录 .env
        if Path(".env").exists():
            return cls.load_from_env(".env")

        # 3. 当前目录 config.toml
        if Path("config.toml").exists():
            return cls.load("config.toml")

        # 4. ~/.acp-link/.env
        home_env = Path.home() / ".acp-link" / ".env"
        if home_env.exists():
            return cls.load_from_env(home_env)

        # 5. ~/.acp-link/config.toml
        home_config = Path.home() / ".acp-link" / "config.toml"
        if home_config.exists():
            return cls.load(home_config)

        raise FileNotFoundError("未找到配置文件")

    @staticmethod
    def data_dir() -> Path:
        """获取数据存储目录"""
        return Path.home() / ".acp-link" / "data"

    @staticmethod
    def log_dir() -> Path:
        """获取日志目录"""
        return Path.home() / ".acp-link" / "logs"

    @staticmethod
    def temp_dir() -> Path:
        """获取临时文件目录"""
        return Path.home() / ".acp-link" / "temp"
