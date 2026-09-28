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

def consultar_lotes_fazenda(nome_ou_numero_lote: str = "") -> str:
    """
    Consulta os lotes de gado cadastrados no banco de dados Firestore.
    Use quando o usuário perguntar quantas cabeças/animais tem em um lote específico (ex: 'quantas cabeças tem no lote 5?'),
    quais lotes existem na fazenda, ou pedir detalhes de um lote.
    Se nome_ou_numero_lote estiver vazio ou for geral, lista todos os lotes cadastrados.
    """
    try:
        if db is None:
            return "Banco de dados Firestore não está conectado no momento."
        
        colecao_lotes = db.collection("lotes_fazenda")
        termo = (nome_ou_numero_lote or "").strip().lower()
        
        # Se um lote específico foi pedido
        if termo and termo not in ["todos", "geral", "tudo", "listar"]:
            id_direto = termo.replace(" ", "_")
            doc = colecao_lotes.document(id_direto).get()
            
            # Se não achou diretamente, tenta prefixo lote_ (ex: '5' -> 'lote_5')
            if not doc.exists and not id_direto.startswith("lote_"):
                doc = colecao_lotes.document(f"lote_{id_direto}").get()
                
            # Se ainda não achou, faz uma busca por aproximação nos documentos
            if not doc.exists:
                for d in colecao_lotes.stream():
                    dados = d.to_dict()
                    nome = str(dados.get("nome_lote", "")).lower()
                    if termo in nome or termo in d.id:
                        doc = d
                        break
                        
            if doc and doc.exists:
                dados = doc.to_dict()
                nome = dados.get("nome_lote", doc.id)
                qtd = dados.get("quantidade_cabecas", 0)
                finalidade = dados.get("finalidade", "não informada")
                status = dados.get("status", "ativo")
                resposta = f"Lote '{nome}': {qtd} cabeças de gado. Finalidade: {finalidade}. Status: {status}."
                
                # Verifica se há registro de cocho recente
                try:
                    doc_consumo = db.collection("consumo_cocho").document(doc.id).get()
                    if doc_consumo.exists:
                        c_dados = doc_consumo.to_dict()
                        acumulado = c_dados.get("consumo_acumulado_kg", 0)
                        ultimo_insumo = c_dados.get("ultimo_insumo", "ração")
                        resposta += f" Consumo acumulado no cocho: {acumulado} kg (Último insumo: {ultimo_insumo})."
                except Exception:
                    pass
                return resposta
            else:
                return f"Não encontrei o lote '{nome_ou_numero_lote}' cadastrado no banco de dados."
                
        # Se pediu todos ou não especificou
        docs = list(colecao_lotes.stream())
        if not docs:
            return "Nenhum lote cadastrado no banco de dados da fazenda até o momento."
            
        resposta = "Lotes cadastrados na fazenda:\n"
        for d in docs:
            dados = d.to_dict()
            nome = dados.get("nome_lote", d.id)
            qtd = dados.get("quantidade_cabecas", 0)
            finalidade = dados.get("finalidade", "não informada")
            status = dados.get("status", "ativo")
            resposta += f"- {nome}: {qtd} cabeças (Finalidade: {finalidade}, Status: {status})\n"
        return resposta.strip()
    except Exception as e:
        return f"Erro ao consultar lotes no banco de dados: {str(e)}"

def listar_bulas_existentes() -> str:
    """
    Lista todos os medicamentos, bulas veterinárias e manuais técnicos disponíveis no banco de dados Firestore.
    Use quando o usuário perguntar quais remédios, bulas ou manuais estão cadastrados no sistema.
    """
    try:
        if db is None:
            return "Banco de dados Firestore não está conectado no momento."
            
        docs = list(db.collection("bulas_conhecimento").stream())
        if not docs:
            return "Nenhuma bula ou manual técnico cadastrado no banco de dados."
            
        medicamentos = set()
        for d in docs:
            med = d.to_dict().get("medicamento")
            if med:
                medicamentos.add(med)
                
        if not medicamentos:
            return "Nenhuma bula identificada na base de conhecimento."
            
        lista_formatada = sorted(list(medicamentos))
        resposta = "Medicamentos e manuais técnicos cadastrados na base de conhecimento:\n"
        for item in lista_formatada:
            resposta += f"- {item}\n"
        resposta += "\nPode me perguntar sobre dosagem, período de carência, modo de aplicação ou indicação de qualquer um deles."
        return resposta
    except Exception as e:
        return f"Erro ao listar bulas no banco de dados: {str(e)}"

def consultar_bula_medicamento(duvida_sintoma_ou_medicamento: str) -> str:
    """
    Busca informações técnicas em bulas veterinárias e manuais (ex: dose, invermectina, carência).
    Use SEMPRE que o usuário fizer perguntas técnicas de saúde animal ou dosagem.
    """
    try:
        if db is None:
            return "Banco de dados de bulas offline no momento."

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
            # Fallback para busca textual simples caso vetor retorne vazio
            termo = duvida_sintoma_ou_medicamento.lower()
            encontrados = []
            for doc in db.collection("bulas_conhecimento").limit(20).stream():
                dados = doc.to_dict()
                med = str(dados.get("medicamento", "")).lower()
                conteudo = str(dados.get("conteudo_texto", ""))
                if termo in med or termo in conteudo.lower():
                    encontrados.append(dados)
                    if len(encontrados) >= 2:
                        break
            if not encontrados:
                return f"Não encontrei informações sobre '{duvida_sintoma_ou_medicamento}' na base de dados das bulas."
            contexto_rag = f"Resultados das bulas para '{duvida_sintoma_ou_medicamento}':\n"
            for dados in encontrados:
                contexto_rag += f"--- {dados.get('medicamento')} ---\n{dados.get('conteudo_texto')}\n\n"
            return contexto_rag

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
            "3. Se o peão mandar registrar consumo ou criar um lote, use as ferramentas correspondentes.\n"
            "4. Se o usuário perguntar quantas cabeças de gado tem em um lote, quais lotes existem ou pedir detalhes de um lote, use OBRIGATORIAMENTE a ferramenta 'consultar_lotes_fazenda'.\n"
            "5. Se o usuário perguntar quais bulas, medicamentos ou manuais estão cadastrados/disponíveis no sistema, use a ferramenta 'listar_bulas_existentes'.\n"
            "6. Se fizerem perguntas sobre dosagem de remédio (ex: Invermectina, vacinas, carência, modo de usar), OBRIGATORIAMENTE use a ferramenta 'consultar_bula_medicamento' antes de responder. Baseie sua resposta apenas no que a ferramenta retornar."
        )

        configuracao_ia = types.GenerateContentConfig(
            # Adicionamos todas as ferramentas que criamos aqui:
            tools=[
                registrar_consumo_cocho,
                criar_lote_engorda,
                consultar_lotes_fazenda,
                listar_bulas_existentes,
                consultar_bula_medicamento
            ],
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

# Rota para consulta direta dos lotes cadastrados
@app.get("/api/lotes")
def listar_lotes_api(usuario: dict = Depends(verificar_token_firebase)):
    try:
        if db is None:
            return {"lotes": [], "mensagem": "Banco de dados Firestore offline."}
        docs = db.collection("lotes_fazenda").stream()
        lotes = []
        for d in docs:
            dados = d.to_dict()
            dados["id"] = d.id
            lotes.append(dados)
        return {"total": len(lotes), "lotes": lotes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar lotes: {str(e)}")

# Rota para consulta direta das bulas cadastradas
@app.get("/api/bulas")
def listar_bulas_api(usuario: dict = Depends(verificar_token_firebase)):
    try:
        if db is None:
            return {"bulas": [], "mensagem": "Banco de dados Firestore offline."}
        docs = db.collection("bulas_conhecimento").stream()
        medicamentos = sorted(list(set(d.to_dict().get("medicamento") for d in docs if d.to_dict().get("medicamento"))))
        return {"total": len(medicamentos), "bulas": medicamentos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar bulas: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)