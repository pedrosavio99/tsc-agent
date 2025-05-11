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

# Expõe a porta definida pela variável de ambiente PORT (padrão 10000 no Render)
EXPOSE 10000

# Comando para rodar a aplicação FastAPI usando a variável PORT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]