import os
import firebase_admin
from firebase_admin import credentials, firestore

def get_firestore_client():
    """
    Inicializa o Firebase Admin SDK e retorna o cliente do Firestore.
    Utiliza o padrão Singleton para evitar múltiplas conexões.
    Permite fallback gracioso em modo de desenvolvimento se as chaves ainda não forem fornecidas.
    """
    if not firebase_admin._apps:
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase-admin-key.json")
        
        # Se for caminho relativo, procura a partir do diretório do backend
        if not os.path.isabs(cred_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            local_path = os.path.join(base_dir, cred_path)
            if os.path.exists(local_path):
                cred_path = local_path
        
        if os.path.exists(cred_path):
            try:
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                print(f"[OK] Conexao com Firebase Firestore estabelecida ({cred_path})")
                return firestore.client()
            except Exception as e:
                print(f"[AVISO] Erro ao inicializar Firebase: {str(e)}")
        else:
            print(f"[INFO] Credenciais do Firebase nao localizadas em '{cred_path}'. Operando em Modo Demonstracao/Offline.")
            
    else:
        try:
            return firestore.client()
        except Exception:
            pass

    return None

# Exportação do cliente Singleton
db = get_firestore_client()