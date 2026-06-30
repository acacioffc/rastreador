import os
import requests
import json
import time
import logging
import sys
from datetime import datetime
from supabase import create_client

# ============================================================
# CONFIGURAÇÕES (lê das variáveis de ambiente)
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ucnjavuxvippfhzjudnv.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
API_TOKEN = os.getenv("API_TOKEN", "1a79a4d8606714545d970c1bc76b7ec2")
API_USER = os.getenv("API_USER", "97244376120")
API_PASS = os.getenv("API_PASS", "97244376120")

API_URL = "https://sistema.localizarastreamento.com/integracao/api/getHistoricosV3.php"
API_HEADERS = {
    "token": API_TOKEN,
    "user": API_USER,
    "pass": API_PASS,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

TABLE_NAME = "cad_rastreador"
BATCH_SIZE = 100

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ============================================================
# FUNÇÕES
# ============================================================
def fetch_historicos(max_retries=3, base_delay=5):
    for attempt in range(max_retries):
        try:
            resp = requests.get(API_URL, headers=API_HEADERS, timeout=30)
            resp.raise_for_status()
            return parse_response(resp.text)
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 429:
                wait = base_delay * (2 ** attempt)
                logger.warning(f"Rate limit (429). Tentando novamente em {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"Erro HTTP {resp.status_code}: {e}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro na requisição: {e}")
            return None
    logger.error("Número máximo de tentativas excedido.")
    return None

def parse_response(raw_text):
    raw_text = raw_text.strip()
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    lines = raw_text.splitlines()
    objetos = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                objetos.append(json.loads(line))
            except:
                pass
    if objetos:
        return objetos

    if raw_text.startswith('{') and '},{' in raw_text:
        try:
            wrapped = '[' + raw_text + ']'
            data = json.loads(wrapped)
            if isinstance(data, list):
                return data
        except:
            pass

    logger.error("Não foi possível interpretar a resposta.")
    logger.debug(f"Trecho: {raw_text[:200]}")
    return None

def upsert_historicos(registros):
    if not registros:
        return 0

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    try:
        for r in registros:
            if "created_at" not in r:
                r["created_at"] = datetime.now().isoformat()

        response = supabase.table(TABLE_NAME).upsert(
            registros,
            on_conflict="id"
        ).execute()
        logger.info(f"✅ {len(registros)} registros enviados (upsert).")
        return len(registros)
    except Exception as e:
        logger.error(f"Erro no upsert: {e}")
        return 0
    finally:
        supabase.postgrest.session.close()

def main():
    logger.info("🚀 Iniciando coleta de dados da API de rastreamento...")

    if not SUPABASE_KEY:
        logger.error("❌ SUPABASE_KEY não definida. Configure a variável de ambiente.")
        return

    dados = fetch_historicos()
    if not dados:
        logger.warning("⚠️ Nenhum dado retornado pela API.")
        return

    logger.info(f"📦 Obtidos {len(dados)} registros da API.")

    total_inseridos = 0
    for i in range(0, len(dados), BATCH_SIZE):
        lote = dados[i:i+BATCH_SIZE]
        inseridos = upsert_historicos(lote)
        total_inseridos += inseridos
        time.sleep(0.2)

    logger.info(f"✅ Processo finalizado. {total_inseridos} registros processados.")

if __name__ == "__main__":
    main()