# Seller Link

사업자등록번호 또는 스마트스토어 URL로 통신판매 공시와 검색 결과를 함께 조회합니다.

## 시작

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

`.env`에 아래 두 값을 채웁니다.

```env
FTC_SERVICE_KEY=공공데이터포털_Decoding_인증키
SERPAPI_KEY=SerpApi_API_Key
NAVER_CLIENT_ID=네이버_검색_API_클라이언트_ID
NAVER_CLIENT_SECRET=네이버_검색_API_클라이언트_시크릿
```

```bash
.venv/bin/uvicorn app.main:app --reload
```

브라우저에서 `http://127.0.0.1:8000`을 엽니다.

## GitHub에서 공개 배포

저장소를 GitHub에 올린 뒤 Render에서 이 저장소를 선택해 배포할 수 있습니다. `render.yaml`을 인식하면 웹 서비스가 생성되며, Render의 Environment 탭에 `FTC_SERVICE_KEY`와 `SERPAPI_KEY`를 다시 Secret으로 입력하면 됩니다. `.env`는 GitHub에 올리지 않습니다.

## 동작

- 사업자등록번호 10자리 또는 스마트스토어 URL 입력
- URL은 공개 HTML 안에서 유효한 사업자등록번호를 추출
- 공정위 통신판매사업자 API에서 공시 정보와 인터넷도메인 조회
- 네이버 웹문서 검색 API로 스마트스토어 검색
- SerpApi로 쿠팡·지마켓·11번가·옥션과 자사몰 검색
- 결과는 입점 확인, 입점 X, 확인 X만 표시합니다.

서비스는 검색 결과를 기반으로 연결을 표시하므로, 결과 페이지의 공개 사업자 정보가 같은 번호인지 확인해야 최종 검증할 수 있습니다.
