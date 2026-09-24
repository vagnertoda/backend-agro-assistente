from firebase_admin import firestore
from infrastructure.firestore_db import db

def registrar_consumo_cocho(lote_id: str, insumo: str, quantidade_kg: float, fazenda_id: str = "fazenda_padrao") -> str:
    """
    Registra o consumo de trato (ração, sal mineral, silagem, concentrado) de um lote no banco de dados.
    Acione esta ferramenta SEMPRE que o usuário afirmar que tratou o gado, encheu o cocho ou forneceu alimento.
    
    Args:
        lote_id: Identificador do lote de animais (ex: 'Lote 1', 'Lote 2', 'Pasto 5').
        insumo: Tipo do alimento fornecido (ex: 'Sal Mineral', 'Ração Concentrada', 'Silagem').
        quantidade_kg: Peso total em quilogramas fornecido (ex: 150.0).
        fazenda_id: Identificador da fazenda (padrão 'fazenda_padrao').
    """
    try:
        if db is not None:
            lote_ref = db.collection("fazendas").document(fazenda_id)\
                         .collection("lotes").document(lote_id)
            
            lote_ref.set({
                "consumo_acumulado_kg": firestore.Increment(quantidade_kg),
                "ultimo_insumo": insumo,
                "ultima_atualizacao": firestore.SERVER_TIMESTAMP
            }, merge=True)
            
            return f"✅ Sucesso: Foram registrados {quantidade_kg} kg de {insumo} no cocho do lote '{lote_id}'."
        else:
            return f"ℹ️ Registro simulado (Modo Offline/Dev): {quantidade_kg} kg de {insumo} computados para o lote '{lote_id}'."
            
    except Exception as e:
        return f"Aviso operacional: Não foi possível gravar no banco agora ({str(e)}), mas anotei que {quantidade_kg} kg de {insumo} foram dados ao lote '{lote_id}'."