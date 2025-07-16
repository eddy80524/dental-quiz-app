FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY ./my_llm_app ./my_llm_app
COPY ./data ./my_llm_app/data

EXPOSE 8501

CMD ["streamlit", "run", "my_llm_app/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
