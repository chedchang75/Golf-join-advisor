# Microsoft Playwright 공식 Python Linux 이미지 (Chromium 브라우저 및 모든 리눅스 라이브러리 100% 사전 내장)
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 환경변수 설정
ENV PYTHONUNBUFFERED=1
ENV PORT=8501

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 전체 소스 코드 복사
COPY . .

# Streamlit 포트 노출
EXPOSE 8501

# Render 웹소켓 및 포트 바인딩 구동 명령어
CMD ["sh", "-c", "streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.enableCORS=false --server.enableXsrfProtection=false"]
