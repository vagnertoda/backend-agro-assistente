import os
from dotenv import load_dotenv # <- 1. Importa a biblioteca
from pydantic import BaseModel
from typing import List, Dict, Any

# 2. Carrega as variáveis de dentro do arquivo .env
load_dotenv() 

from google import genai
from google.genai import types
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from core.seguranca import verificar_token_firebase
from infrastructure.firestore_db import db

# =================================================================
# 1. CONTRATOS (Pydantic Schema)
# =================================================================
class ComandoPWA(BaseModel):
    mensagem: str
    historico: List[Dict[str, Any]] = []

# =================================================================
# 2. CONFIGURAÇÃO DA API DO GEMINI
# =================================================================
chave_gemini = os.getenv("GEMINI_API_KEY") 
client = genai.Client(api_key=chave_gemini)

# chave_gemini = os.getenv("GEMINI_API_KEY")
# if not chave_gemini or chave_gemini == "sua_chave_gemini_aqui":
#    chave_gemini = "sua_chave_gemini_aqui"
#client = genai.Client(
#    api_key=chave_gemini, #insira sua chave API do gemini aqui
#    http_options=types.HttpOptions(
#        retry_options=types.HttpRetryOptions(attempts=1)
#    )
#)

# =================================================================
# 3. FERRAMENTAS PARA A INTELIGÊNCIA ARTIFICIAL (MCP / NATIVAS)
# =================================================================

def registrar_consumo_cocho(lote_id: str, insumo: str, quantidade_kg: float) -> str:
    """
    Registra o consumo de trato (ração, sal mineral, silagem) de um lote no banco de dados Firestore.
    Use sempre que o peão relatar que tratou o gado, colocou ração ou sal no cocho.
    """
    try:
        if db is not None:
            from firebase_admin import firestore
            id_doc = lote_id.replace(" ", "_").lower()
            lote_ref = db.collection("consumo_cocho").document(id_doc)
            
            lote_ref.set({
                "lote": lote_id,
                "consumo_acumulado_kg": firestore.Increment(quantidade_kg),
                "ultimo_insumo": insumo,
                "ultima_quantidade_kg": quantidade_kg,
                "ultima_atualizacao": firestore.SERVER_TIMESTAMP
            }, merge=True)
            
            # Registra no histórico detalhado de tratos
            db.collection("historico_tratos").add({
                "lote": lote_id,
                "insumo": insumo,
                "quantidade_kg": quantidade_kg,
                "data_hora": firestore.SERVER_TIMESTAMP
            })
            
            print(f"[TOOL] Trato de {quantidade_kg}kg de {insumo} salvo com sucesso no Firestore!")
            return f"Sucesso: {quantidade_kg}kg de {insumo} foram registrados e gravados no banco de dados para o lote {lote_id}."
        else:
            return f"Sucesso simulado: {quantidade_kg}kg de {insumo} anotados para o lote {lote_id}."
    except Exception as e:
        return f"Erro ao gravar consumo no banco de dados: {str(e)}"

def criar_lote_engorda(numero_ou_nome_lote: str, quantidade_animais: int, finalidade: str) -> str:
    """
    Cria um novo lote de gado na fazenda e salva no banco de dados.
    Use esta ferramenta quando o usuário pedir para 'criar lote', 'adicionar lote' ou 'cadastrar bois'.
    """
    try:
        colecao_lotes = db.collection("lotes_fazenda")
        id_documento = numero_ou_nome_lote.replace(" ", "_").lower()
        
        # Salvando no Firestore
        colecao_lotes.document(id_documento).set({
            "nome_lote": numero_ou_nome_lote,
            "quantidade_cabecas": quantidade_animais,
            "finalidade": finalidade,
            "status": "ativo"
        })
        print(f"[TOOL] Lote {numero_ou_nome_lote} criado com {quantidade_animais} cabecas no banco!")
        return f"Sucesso: O lote {numero_ou_nome_lote} com {quantidade_animais} animais ({finalidade}) foi criado no sistema."
    except Exception as e:
        return f"Erro ao criar lote no banco de dados: {str(e)}"

def consultar_bula_medicamento(duvida_sintoma_ou_medicamento: str) -> str:
    """
    Busca informações técnicas em bulas veterinárias e manuais (ex: dose, invermectina, carência).
    Use SEMPRE que o usuário fizer perguntas técnicas de saúde animal ou dosagem.
    """
    try:
        # 1. Transforma a pergunta em vetor
        resposta_vetor = client.models.embed_content(
            model='gemini-embedding-001',
            contents=duvida_sintoma_ou_medicamento,
            config=types.EmbedContentConfig(output_dimensionality=768)
        )
        vetor_busca = resposta_vetor.embeddings[0].values
        
        # 2. Busca Vetorial no Firestore (os 2 trechos mais parecidos)
        resultados = db.collection("bulas_conhecimento").find_nearest(
            vector_field="embedding",
            query_vector=Vector(vetor_busca),
            distance_measure=DistanceMeasure.COSINE,
            limit=2
        ).get()
        
        if not resultados:
            return "Não encontrei informações sobre isso na base de dados das bulas."

        contexto_rag = f"Resultados das bulas para '{duvida_sintoma_ou_medicamento}':\n"
        for doc in resultados:
            dados = doc.to_dict()
            contexto_rag += f"--- {dados.get('medicamento')} ---\n{dados.get('conteudo_texto')}\n\n"
        
        return contexto_rag
    except Exception as e:
        return f"Erro ao buscar na base veterinária: {str(e)}"

# =================================================================
# 4. FASTAPI E ROTAS
# =================================================================
app = FastAPI(title="API AgroAssistente")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.post("/api/comando-assistente")
def processar_comando_ia(payload: ComandoPWA, usuario: dict = Depends(verificar_token_firebase)):
    try:
        # A. Preparando o histórico (mantém as últimas 6 mensagens para rapidez e economia de tokens)
        historico_recente = payload.historico[-6:] if len(payload.historico) > 6 else payload.historico
        historico_formatado = []
        for msg in historico_recente:
            texto = msg.get("parts", [""])[0] 
            historico_formatado.append(types.Content(role=msg["role"], parts=[types.Part.from_text(text=texto)]))

        # B. Melhorando o Comportamento (System Prompt) com o usuário autenticado
        nome_usuario = usuario.get("name") or usuario.get("email") or "companheiro"
        instrucao_melhorada = (
            f"Você é o 'AgroAssistente', um zootecnista parceiro do homem do campo. "
            f"O usuário autenticado com conta Google é: {nome_usuario}. "
            "SUAS REGRAS DE COMPORTAMENTO:\n"
            "1. Fale de forma simples, direta e educada, usando leve linguajar caipira, mas sem exageros caricatos.\n"
            "2. Seja MUITO RESUMIDO. Não dê respostas longas. Vá direto ao ponto.\n"
            "3. Se o peão mandar registrar consumo ou criar um lote, use as ferramentas disponíveis.\n"
            "4. Se fizerem perguntas sobre dosagem de remédio (ex: Invermectina, vacinas), OBRIGATORIAMENTE use a ferramenta 'consultar_bula_medicamento' antes de responder. Baseie sua resposta apenas no que a ferramenta retornar."
        )

        configuracao_ia = types.GenerateContentConfig(
            # Adicionamos todas as ferramentas que criamos aqui:
            tools=[registrar_consumo_cocho, criar_lote_engorda, consultar_bula_medicamento],
            system_instruction=instrucao_melhorada,
            temperature=0.3 # Mantém a IA mais focada e menos "inventiva"
        )
                
        # C. Chamada para a IA com suporte a modelo configurável e fallback
        modelo_configurado = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        modelos_candidatos = [modelo_configurado]
        for m in ["gemini-3.5-flash", "gemini-3.6-flash"]:
            if m not in modelos_candidatos:
                modelos_candidatos.append(m)

        resposta_texto = None
        ultimo_erro = None

        for modelo in modelos_candidatos:
            try:
                chat = client.chats.create(model=modelo, config=configuracao_ia, history=historico_formatado)
                resposta_ia = chat.send_message(payload.mensagem)
                resposta_texto = resposta_ia.text
                break
            except Exception as err:
                ultimo_erro = err
                erro_str = str(err)
                if "429" in erro_str or "RESOURCE_EXHAUSTED" in erro_str or "503" in erro_str:
                    print(f"[AVISO] Modelo {modelo} indisponível ou com cota esgotada ({erro_str[:80]}). Tentando próximo modelo...")
                    continue
                raise err

        if resposta_texto is None:
            dev_mode = os.getenv("DEV_MODE", "false").lower() in ("true", "1", "yes")
            if dev_mode and ("429" in str(ultimo_erro) or "RESOURCE_EXHAUSTED" in str(ultimo_erro)):
                resposta_texto = (
                    "Ô companheiro, a cota gratuita diária da chave do Gemini foi atingida temporariamente (limite de requisições do Google AI Studio). "
                    "Para uso contínuo e sem limite compartilhado, adicione sua própria chave `GEMINI_API_KEY` no arquivo `backend/.env` obtida em https://aistudio.google.com/apikey."
                )
            else:
                raise HTTPException(status_code=500, detail=f"Erro na IA: {str(ultimo_erro)}")

        return {
            "resposta_ia": resposta_texto, 
            "autorizado": True,
            "usuario": nome_usuario
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na IA: {str(e)}")

# Rota pública para o Front-end verificar se a API está no ar
@app.get("/api/health")
def health_check():
    return {
        "status": "online", 
        "mensagem": "API do AgroAssistente operando 100%!"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)