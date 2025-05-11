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

app = FastAPI()

# Configurar templates e arquivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Carregar modelos Whisper
model_pt = whisper.load_model("base")  # Modelo português
model_en = whisper.load_model("base.en")  # Modelo inglês

# Configurações da API do Gemini
GEMINI_API_KEY = "AIzaSyBhi0i76UQGAR7YuduQMS74BfCBjdsGQr4"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"

@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/transcribe", response_class=JSONResponse)
async def transcribe_audio(file: UploadFile = File(...), lang: str = Form(...)):
    # Verificar extensão do arquivo
    suffix = os.path.splitext(file.filename)[1]
    if suffix.lower() not in ['.webm', '.mp3', '.wav']:
        raise HTTPException(status_code=400, detail="Formato de arquivo não suportado.")

    # Salvar arquivo temporário
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    wav_path = tmp_path + ".wav"
    try:
        # Converter para WAV
        (
            ffmpeg
            .input(tmp_path)
            .output(wav_path, format="wav", acodec="pcm_s16le", ac=1, ar="16000")
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        os.remove(tmp_path)
        raise HTTPException(status_code=500, detail=f"Erro na conversão de áudio: {str(e)}")

    # Transcrever com o modelo apropriado
    try:
        if lang == "pt":
            result = model_pt.transcribe(wav_path)
        elif lang == "en":
            result = model_en.transcribe(wav_path)
        else:
            raise HTTPException(status_code=400, detail="Idioma não suportado.")
        transcribed_text = result["text"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na transcrição: {str(e)}")
    finally:
        # Limpar arquivos temporários
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        if os.path.exists(wav_path):
            os.remove(wav_path)

    return {"transcribed_text": transcribed_text}

@app.post("/chat", response_class=JSONResponse)
async def chat(text: str = Form(...), language: str = Form(...), context: str = Form(...), history: str = Form("")):
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
            return {"answer": answer}
        else:
            raise HTTPException(status_code=500, detail="Nenhuma resposta válida retornada pela API do Gemini")
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erro ao chamar a API do Gemini: {str(e)}")

@app.post("/generate_audio", response_class=FileResponse)
async def generate_audio(text: str = Form(...), language: str = Form(...)):
    try:
        tts = gTTS(text=text, lang=language, slow=False)
        audio_file = "output.mp3"
        tts.save(audio_file)
        return FileResponse(audio_file, media_type="audio/mpeg", filename="output.mp3")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar áudio: {str(e)}")