import os
import glob
import sys
import time
from pypdf import PdfReader
from google import genai
from google.genai import types
from google.cloud.firestore_v1.vector import Vector

# 1. Configuração de Caminhos (Para ele achar o banco de dados e os PDFs)
# Isso permite rodar o script de qualquer lugar dentro do backend
DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
DIRETORIO_BACKEND = os.path.dirname(DIRETORIO_ATUAL)
sys.path.append(DIRETORIO_BACKEND)

from infrastructure.firestore_db import db

PASTA_PDFS = os.path.join(DIRETORIO_BACKEND, "dados", "manuais_pdf")

# 2. Configuração do Gemini (Novo SDK)
chave_gemini = os.getenv("GEMINI_API_KEY", "sua_chave_gemini_aqui")
client = genai.Client(api_key=chave_gemini)

def extrair_texto(caminho_arquivo: str) -> str:
    """Abre o PDF e extrai todo o texto dele."""
    leitor = PdfReader(caminho_arquivo)
    texto_completo = ""
    for pagina in leitor.pages:
        texto = pagina.extract_text()
        if texto:
            texto_completo += texto + "\n"
    return texto_completo

def quebrar_em_chunks(texto: str, tamanho: int = 1500) -> list:
    """Quebra o texto gigante em pedaços menores (chunks) para a IA não se perder."""
    pedacos = []
    for i in range(0, len(texto), tamanho):
        pedacos.append(texto[i:i+tamanho])
    return pedacos

def rodar_ingestao():
    print(f"🔍 Procurando PDFs na pasta: {PASTA_PDFS}")
    arquivos_pdf = glob.glob(os.path.join(PASTA_PDFS, "*.pdf"))
    
    if not arquivos_pdf:
        print("⚠️ Nenhum PDF encontrado! Coloque arquivos na pasta dados/manuais_pdf.")
        return

    colecao = db.collection("bulas_conhecimento")

    for arquivo in arquivos_pdf:
        nome_arquivo = os.path.basename(arquivo)
        nome_medicamento = nome_arquivo.replace(".pdf", "")
        print(f"\n📄 Processando: {nome_arquivo}...")
        
        texto = extrair_texto(arquivo)
        chunks = quebrar_em_chunks(texto)
        
        for i, chunk in enumerate(chunks):
            # Ignora pedaços vazios ou com muito pouco texto
            if len(chunk.strip()) < 50: 
                continue
                
            print(f"  -> Gerando vetor (embedding) para o trecho {i+1}/{len(chunks)}...")
            
            # Chama a API do Gemini para gerar o Embedding
            resposta = client.models.embed_content(
                model='gemini-embedding-001',
                contents=chunk,
                config=types.EmbedContentConfig(
                    output_dimensionality=768
                )
            )
            
            # O NOVO PULO DO GATO: Faz o script dormir 4 segundos para não estourar a cota gratuita do Google
            time.sleep(4)
            
            # O novo SDK retorna a lista de vetores. Pegamos os valores (lista de floats)
            vetor_matematico = resposta.embeddings[0].values
            
            # Salva no Firebase Firestore
            id_documento = f"{nome_medicamento}_parte_{i+1}".replace(" ", "_").lower()
            doc_ref = colecao.document(id_documento)
            
            doc_ref.set({
                "medicamento": nome_medicamento,
                "topico": f"Trecho {i+1}",
                "conteudo_texto": chunk,
                # Salva como um formato Vector do Firestore para permitir busca semântica depois
                "embedding": Vector(vetor_matematico) 
            })
            
    print("\n✅ Ingestão Concluída! Todos os PDFs foram vetorizados e salvos no banco de dados.")

if __name__ == "__main__":
    rodar_ingestao()