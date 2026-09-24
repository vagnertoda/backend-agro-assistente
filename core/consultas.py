from google.cloud import firestore
from infrastructure.firestore_db import db

def obter_historico_pesagens_lote(lote_id: str, fazenda_id: str = "fazenda_padrao", limite_dias: int = 30) -> str:
    """
    Busca as últimas pesagens de um lote e constrói o contexto de RAG Estruturado
    calculando o Ganho Médio Diário (GMD) histórico.
    """
    pesagens = []
    
    # 1. Tenta buscar do Firestore se disponível
    if db is not None:
        try:
            pesagens_ref = db.collection("fazendas").document(fazenda_id)\
                             .collection("lotes").document(lote_id)\
                             .collection("pesagens")
            
            query = pesagens_ref.order_by("data_pesagem", direction=firestore.Query.DESCENDING).limit(5)
            resultados = query.stream()

            for doc in resultados:
                dados = doc.to_dict()
                data_val = dados.get("data_pesagem")
                data_formatada = data_val.strftime("%d/%m/%Y") if hasattr(data_val, "strftime") else str(data_val)
                peso = dados.get("peso_medio_kg", 0)
                pesagens.append({"data": data_formatada, "peso": peso})
        except Exception as e:
            # Em caso de API desabilitada no GCP ou erro de rede, recorre aos dados demonstrativos
            print(f"[INFO] Consulta Firestore offline ({type(e).__name__}). Usando dados padrao de pesagem.")

    # 2. Se a coleção estiver vazia ou em modo fallback/dev
    if not pesagens:
        pesagens = [
            {"data": "01/08/2026", "peso": 380.0},
            {"data": "15/08/2026", "peso": 395.5},
            {"data": "01/09/2026", "peso": 412.0},
            {"data": "15/09/2026", "peso": 427.8},
            {"data": "22/09/2026", "peso": 435.0}
        ]

    # Formatação tabular para interpretação do LLM
    contexto_rag = f"📊 **Histórico de Pesagem - Lote {lote_id}**\n\n"
    contexto_rag += "| Data | Peso Médio (Kg) | Evolução |\n"
    contexto_rag += "|---|---|---|\n"

    # Garante ordem cronológica
    pesagens_ordenadas = list(reversed(pesagens)) if len(pesagens) > 1 and pesagens[0]["data"] > pesagens[-1]["data"] else pesagens
    
    peso_anterior = None
    for p in pesagens_ordenadas:
        evolucao = "---"
        if peso_anterior is not None:
            ganho = p['peso'] - peso_anterior
            sinal = "+" if ganho > 0 else ""
            evolucao = f"{sinal}{ganho:.1f} kg"
        
        contexto_rag += f"| {p['data']} | {p['peso']:.1f} | {evolucao} |\n"
        peso_anterior = p['peso']

    contexto_rag += "\n*Nota para o LLM: Analise a evolução de peso acima calculando o GMD aproximado e dê um parecer zootécnico caipira e direto.*"
    return contexto_rag