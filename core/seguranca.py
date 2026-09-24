import os
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth
import firebase_admin

load_dotenv()

security = HTTPBearer(auto_error=False)

def verificar_token_firebase(credenciais: HTTPAuthorizationCredentials = Depends(security)):
    """
    Dependência que intercepta o token JWT do Firebase e valida a assinatura criptográfica.
    Permite bypass seguro no modo DEV_MODE para desenvolvimento e testes locais.
    """
    dev_mode = os.getenv("DEV_MODE", "false").lower() in ("true", "1", "yes")

    # Tratamento para ausência de cabeçalho: sempre exige login
    if not credenciais or not credenciais.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acesso negado: somente usuários autenticados com conta Google podem acessar o assistente."
        )

    token = credenciais.credentials

    # Suporte a tokens de desenvolvimento com dados do Google em DEV_MODE
    if dev_mode and (token in ("dev-token", "teste-token", "mock-token") or token.startswith("google-demo-token:")):
        nome = "Produtor Google"
        email = "produtor@gmail.com"
        if token.startswith("google-demo-token:"):
            partes = token.split(":", 2)
            if len(partes) >= 2 and partes[1]:
                email = partes[1]
            if len(partes) >= 3 and partes[2]:
                nome = partes[2]
        return {
            "uid": f"google_dev_{abs(hash(email))}",
            "email": email,
            "name": nome
        }

    try:
        # Se o app Firebase estiver inicializado, valida no servidor do Google
        if firebase_admin._apps:
            usuario_decodificado = auth.verify_id_token(token)
            return usuario_decodificado
        elif dev_mode:
            return {
                "uid": "dev_offline_01",
                "email": "offline@fazenda.com",
                "name": "Operador Offline"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Serviço de autenticação Firebase não inicializado no servidor."
            )

    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado. O PWA precisa renovar o login."
        )
    except auth.InvalidIdTokenError:
        if dev_mode:
            return {
                "uid": "dev_capataz_01",
                "email": "capataz@fazenda.com",
                "name": "Capataz da Fazenda (Dev)"
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação inválido ou forjado."
        )
    except Exception as e:
        if dev_mode:
            return {
                "uid": "dev_capataz_01",
                "email": "capataz@fazenda.com",
                "name": "Capataz da Fazenda (Dev)"
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Falha na validação do crachá de segurança: {str(e)}"
        )