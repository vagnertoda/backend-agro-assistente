import os
from infrastructure.firestore_db import db

# Base de conhecimento de fallback com bulas veterinárias essenciais para pecuária de corte
BASE_BULAS_FALLBACK = {
    "ivomec": {
        "medicamento": "Ivomec (Ivermectina 1%)",
        "indicacao": "Tratamento e controle de parasitas internos (nematódeos gastrointestinais e pulmonares) e externos (berne, sarna e carrapatos).",
        "dosagem": "1 mL para cada 50 kg de peso vivo, via subcutânea exclusiva (na tábua do pescoço).",
        "carencia": "Carência para abate: 35 dias após a última aplicação. Não administrar em fêmeas leiteiras em lactação.",
        "precaucoes": "Não aplicar por via endovenosa ou intramuscular. Proteger da luz solar direta."
    },
    "dectomax": {
        "medicamento": "Dectomax (Doramectina 1%)",
        "indicacao": "Endectocida de amplo espectro para bovinos. Eficaz contra carrapatos, bernes, miíases (bicheiras) e vermes redondos.",
        "dosagem": "1 mL para cada 50 kg de peso vivo, administrado por via subcutânea ou intramuscular.",
        "carencia": "Carência para abate: 35 dias para via subcutânea e 49 dias para intramuscular. Não usar em vacas leiteiras cujo leite seja destinado ao consumo humano.",
        "precaucoes": "Manter a agulha limpa e trocar a cada 10 a 15 animais para evitar abcessos."
    },
    "terramicina": {
        "medicamento": "Terramicina LA (Oxitetraciclina)",
        "indicacao": "Antibiótico de ação prolongada para pneumonia, pododermatite (foot-rot), anaplasmose, queratoconjuntivite e diarreias bacterianas.",
        "dosagem": "1 mL para cada 10 kg de peso vivo (20 mg/kg), via intramuscular profunda.",
        "carencia": "Carência para abate: 28 dias após a última aplicação. Leite: carência de 7 dias.",
        "precaucoes": "Não aplicar mais de 10 mL no mesmo ponto de injeção para evitar lesões musculares."
    },
    "borgan": {
        "medicamento": "Borgal (Sulfadoxina + Trimetoprima)",
        "indicacao": "Tratamento de infecções bacterianas agudas, pneumonias, infecções urinárias e diarreia dos bezerros.",
        "dosagem": "3 mL para cada 50 kg de peso vivo, via intramuscular, intravenosa ou subcutânea.",
        "carencia": "Carência para abate: 5 dias após a última aplicação. Leite: 48 horas.",
        "precaucoes": "Aplicar a via intravenosa de forma lenta."
    }
}

def consultar_bula_medicamento(duvida_sintoma_ou_medicamento: str) -> str:
    """
    Busca informações técnicas, princípios ativos, dosagens e períodos de carência em bulas veterinárias.
    
    Acione esta ferramenta SEMPRE que o peão ou capataz perguntar sobre:
    - Como tratar doenças do gado (ex: 'gado tossindo', 'bezerro com diarreia', 'bicheira', 'carrapato').
    - Qual remédio aplicar e dosagem em ml ou mg por peso (ex: 'quantos ml de Ivomec?').
    - Qual o período de carência para abate ou leite antes de enviar animais ao frigorífico.
    
    Args:
        duvida_sintoma_ou_medicamento: Texto da dúvida, nome da enfermidade ou medicamento pesquisado.
    """
    termo = duvida_sintoma_ou_medicamento.lower()
    
    # 1. Tenta busca vetorial no Firestore caso disponível
    if db is not None:
        try:
            from google.cloud.firestore_v1.vector import Vector
            from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
            from google import genai
            
            chave_gemini = os.getenv("GEMINI_API_KEY")
            if chave_gemini and chave_gemini != "sua_chave_gemini_aqui":
                client = genai.Client(api_key=chave_gemini)
                embedding_resp = client.models.embed_content(
                    model="text-embedding-004",
                    contents=duvida_sintoma_ou_medicamento
                )
                vetor = embedding_resp.embedding.values
                
                colecao_bulas = db.collection("bulas_conhecimento")
                resultados = colecao_bulas.find_nearest(
                    vector_field="embedding",
                    query_vector=Vector(vetor),
                    distance_measure=DistanceMeasure.COSINE,
                    limit=2
                ).get()
                
                if resultados:
                    contexto = f"📚 **Base de Bulas Veterinárias (Busca Vetorial):**\n\n"
                    for doc in resultados:
                        d = doc.to_dict()
                        contexto += f"### {d.get('medicamento', 'Medicamento')}\n"
                        contexto += f"{d.get('conteudo_texto', '')}\n\n"
                    contexto += "\n*Alerta Obrigatório: Recomende sempre validação com o médico veterinário responsável pela fazenda.*"
                    return contexto
        except Exception:
            # Fallback transparente para a base curada
            pass

    # 2. Busca na base curada de alta fidelidade
    encontrados = []
    for chave, bula in BASE_BULAS_FALLBACK.items():
        if (chave in termo or 
            bula["medicamento"].lower() in termo or 
            any(w in termo for w in ["ivomec", "ivermectina"] if "ivomec" in chave) or
            any(w in termo for w in ["dectomax", "doramectina", "carrapato", "bicheira"] if "dectomax" in chave) or
            any(w in termo for w in ["terramicina", "oxitetraciclina", "pneumonia", "tosse", "manqueira"] if "terramicina" in chave) or
            any(w in termo for w in ["borgal", "diarreia", "bezerro"] if "borgan" in chave)):
            encontrados.append(bula)

    if not encontrados:
        # Se nenhuma palavra-chave específica bater, devolve catálogo geral resumido
        encontrados = list(BASE_BULAS_FALLBACK.values())[:2]

    contexto = f"📚 **Guia Técnico de Saúde Animal - Bula Informativa:**\n\n"
    for bula in encontrados:
        contexto += f"### 💊 {bula['medicamento']}\n"
        contexto += f"- **Indicação:** {bula['indicacao']}\n"
        contexto += f"- **Dosagem Recomendada:** {bula['dosagem']}\n"
        contexto += f"- **Período de Carência:** {bula['carencia']}\n"
        contexto += f"- **Precauções no Manejo:** {bula['precaucoes']}\n\n"

    contexto += "*Instrução para IA: Sintetize as informações em linguagem caipira e direta. É OBRIGATÓRIO lembrar o peão de conferir com o veterinário da fazenda antes da aplicação.*"
    return contexto