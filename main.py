from fastapi import FastAPI, Form, Request, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import whisper
import ffmpeg
import tempfile
import os
import requests
from gtts import gTTS
import logging
import time

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Configurar templates e arquivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Carregar modelo em inglês na inicialização
logger.info("Carregando modelo Whisper tiny.en na inicialização")
model_en = whisper.load_model("tiny.en")  # Carrega tiny.en no startup
model_pt = None  # Português sob demanda

# Função para carregar modelo (apenas português, se necessário)
def load_model(lang: str):
    global model_pt, model_en
    if lang == "pt" and model_pt is None:
        logger.info("Carregando modelo Whisper tiny para português")
        model_pt = whisper.load_model("tiny")  # Modelo menor para português
    return model_pt if lang == "pt" else model_en

# Chave da API do Gemini (hardcoded, conforme solicitado)
GEMINI_API_KEY = "AIzaSyBhi0i76UQGAR7YuduQMS74BfCBjdsGQr4"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"

# Health check para o Render
@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/transcribe", response_class=JSONResponse)
async def transcribe_audio(file: UploadFile = File(...), lang: str = Form(...)):
    start_time = time.time()
    logger.info(f"Iniciando transcrição para idioma: {lang}, arquivo: {file.filename}")

    # Verificar extensão do arquivo
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix not in ['.webm', '.mp3', '.wav']:
        logger.error(f"Formato de arquivo não suportado: {suffix}")
        raise HTTPException(status_code=400, detail="Formato de arquivo não suportado.")

    # Verificar tamanho do arquivo (máximo 5 MB)
    content = await file.read()
    file_size_mb = len(content) / (1024 * 1024)
    if file_size_mb > 5:
        logger.error(f"Arquivo muito grande: {file_size_mb:.2f} MB")
        raise HTTPException(status_code=400, detail="Arquivo excede o limite de 5 MB.")

    # Salvar arquivo temporário
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    logger.info(f"Arquivo temporário salvo: {tmp_path}")

    wav_path = tmp_path + ".wav"
    try:
        # Converter para WAV com limite de duração (máximo 30 segundos)
        logger.info("Convertendo áudio para WAV")
        try:
            stream = ffmpeg.input(tmp_path)
            stream = ffmpeg.output(
                stream,
                wav_path,
                format="wav",
                acodec="pcm_s16le",
                ac=1,
                ar="16000",
                t=30,  # Limitar a 30 segundos
                loglevel="error"
            )
            ffmpeg.run(stream, overwrite_output=True)  # Removido o argumento timeout
            logger.info(f"Conversão concluída: {wav_path}")
        except ffmpeg.Error as e:
            logger.error(f"Erro na conversão de áudio: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Erro na conversão de áudio: {str(e)}")

        # Verificar se o arquivo WAV foi criado
        if not os.path.exists(wav_path):
            logger.error("Arquivo WAV não foi criado")
            raise HTTPException(status_code=500, detail="Falha ao criar arquivo WAV.")

        # Carregar o modelo (inglês já está carregado, português sob demanda)
        logger.info("Carregando modelo Whisper")
        model = load_model(lang)
        if model is None:
            logger.error("Idioma não suportado")
            raise HTTPException(status_code=400, detail="Idioma não suportado.")

        # Transcrição
        logger.info("Iniciando transcrição")
        try:
            result = model.transcribe(wav_path)
            transcribed_text = result["text"].strip()
            if not transcribed_text:
                logger.warning("Transcrição retornou texto vazio")
                raise HTTPException(status_code=500, detail="Transcrição retornou texto vazio.")
            logger.info(f"Transcrição concluída em {time.time() - start_time:.2f}s: {transcribed_text}")
        except Exception as e:
            logger.error(f"Erro na transcrição: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Erro na transcrição: {str(e)}")

    except Exception as e:
        logger.error(f"Erro geral na transcrição: {str(e)}")
        raise
    finally:
        # Limpar arquivos temporários
        for path in [tmp_path, wav_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logger.info(f"Arquivo removido: {path}")
                except Exception as e:
                    logger.warning(f"Falha ao remover arquivo {path}: {str(e)}")

    return {"transcribed_text": transcribed_text}

@app.post("/chat", response_class=JSONResponse)
async def chat(text: str = Form(...), language: str = Form(...), context: str = Form(...), history: str = Form("")):
    logger.info(f"Iniciando chat, idioma: {language}, contexto: {context}")
    # Definir instrução de idioma
    lang_instruction = "Responda em português" if language == "pt" else "Respond in English"

    # Configurar contexto
    if context == "job_interview":
        context_desc = (
            "Você é um entrevistador profissional conduzindo uma entrevista de emprego. "
            "Responda de forma direta, profissional e natural, como um entrevistador real, "
            "focando em perguntas ou respostas relevantes à entrevista, como currículo, habilidades ou experiências. "
            "Evite saudações genéricas, apresentações ou frases desnecessárias."
        )
    elif context == "airport":
        context_desc = (
            "Você é um funcionário de um aeroporto ajudando um passageiro. "
            "Responda de forma clara, útil e natural, como um atendente real, "
            "sobre voos, check-in, bagagem, segurança ou navegação no aeroporto. "
            "Evite saudações genéricas ou frases desnecessárias."
        )
    else:
        context_desc = (
            f"Você está respondendo em um contexto personalizado: {context}. "
            "Responda de forma direta, natural e relevante ao contexto fornecido, "
            "evitando saudações genéricas, apresentações ou frases desnecessárias."
        )

    # Construir o prompt otimizado
    prompt = (
        f"{lang_instruction}. {context_desc}\n\n"
        "Instruções adicionais: Responda de forma concisa, simulando uma interação real no contexto especificado. "
        "Não inclua saudações como 'Olá', 'Prazer em conhecê-lo' ou frases genéricas de apresentação, "
        "a menos que explicitamente solicitado. Mantenha o foco na pergunta ou no diálogo atual.\n\n"
        f"Histórico da conversa:\n{history}\n\n"
        f"Pergunta ou diálogo atual: {text}"
    )

    # Configurar a requisição para a API do Gemini
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "topP": 0.95,
            "maxOutputTokens": 512
        }
    }

    try:
        response = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        result = response.json()

        # Extrair a resposta
        if "candidates" in result and len(result["candidates"]) > 0:
            answer = result["candidates"][0]["content"]["parts"][0]["text"].strip()
            logger.info(f"Resposta do Gemini: {answer}")
            return {"answer": answer}
        else:
            logger.error("Nenhuma resposta válida retornada pela API do Gemini")
            raise HTTPException(status_code=500, detail="Nenhuma resposta válida retornada pela API do Gemini")
    except requests.RequestException as e:
        logger.error(f"Erro ao chamar a API do Gemini: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao chamar a API do Gemini: {str(e)}")

@app.post("/generate_audio", response_class=FileResponse)
async def generate_audio(text: str = Form(...), language: str = Form(...)):
    logger.info(f"Gerando áudio para texto: {text[:50]}..., idioma: {language}")
    try:
        tts = gTTS(text=text, lang=language, slow=False)
        audio_file = "output.mp3"
        tts.save(audio_file)
        logger.info(f"Áudio gerado: {audio_file}")
        return FileResponse(audio_file, media_type="audio/mpeg", filename="output.mp3")
    except Exception as e:
        logger.error(f"Erro ao gerar áudio: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar áudio: {str(e)}")