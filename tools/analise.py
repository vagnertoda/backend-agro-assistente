from core.consultas import obter_historico_pesagens_lote

def analisar_ganho_peso(lote_id: str, fazenda_id: str = "fazenda_padrao") -> str:
    """
    Recupera e analisa o histórico de peso e a evolução ponderal (GMD) de um lote de animais.
    
    Acione esta ferramenta SEMPRE que o capataz perguntar sobre:
    - O peso atual do gado ou do lote.
    - Se a boiada está engordando, mantendo ou perdendo peso.
    - O ganho médio diário (GMD) ou desempenho de um lote específico.
    
    Args:
        lote_id: Identificador do lote (ex: 'Lote 1', 'Lote Nelore', 'Lote 3').
        fazenda_id: Identificador da fazenda (padrão 'fazenda_padrao').
    """
    return obter_historico_pesagens_lote(lote_id=lote_id, fazenda_id=fazenda_id)