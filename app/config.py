from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    ftc_service_key: str = os.getenv("FTC_SERVICE_KEY", "")
    serpapi_key: str = os.getenv("SERPAPI_KEY", "")
    naver_client_id: str = os.getenv("NAVER_CLIENT_ID", "")
    naver_client_secret: str = os.getenv("NAVER_CLIENT_SECRET", "")
    ftc_detail_endpoint: str = os.getenv(
        "FTC_DETAIL_ENDPOINT",
        "https://apis.data.go.kr/1130000/MllBs_2Service/getMllBsBiznoInfo_2",
    )
    request_timeout_seconds: float = 15.0


settings = Settings()
