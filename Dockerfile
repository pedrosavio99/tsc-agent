# Usa uma imagem Python oficial como base
FROM python:3.10-slim

# Define o diretório de trabalho
WORKDIR /app

# Instala dependências de sistema, incluindo ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copia o requirements.txt
COPY requirements.txt .

# Instala as dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY . .

# Expõe a porta 8080 (padrão do Cloud Run)
EXPOSE 8080

# Comando para rodar a aplicação FastAPI usando a variável PORT (padrão 8080 no Cloud Run)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]