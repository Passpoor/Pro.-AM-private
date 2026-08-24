# config_base.py - 共享配置（邮箱、期刊白名单）

import os

# ========== 期刊白名单（中科院1区顶刊） ==========
JOURNALS_CAS1 = (
    # --- Nature 系列 ---
    '"Nature"[Journal] OR '
    '"Nature Immunol*"[Journal] OR '
    '"Nature Med*"[Journal] OR '
    '"Nature Cell Biol*"[Journal] OR '
    '"Nature Commun*"[Journal] OR '
    '"Nat Rev Immunol*"[Journal] OR '
    '"Nat Rev Mol Cell Biol*"[Journal] OR '
    '"Nat Rev Cancer"[Journal] OR '
    '"Nat Rev Drug Discov*"[Journal] OR '
    '"Nat Rev Dis Primers"[Journal] OR '
    '"Nat Rev Microbiol*"[Journal] OR '
    '"Nat Rev Genet*"[Journal] OR '
    '"Nat Rev Clin Oncol*"[Journal] OR '
    '"Nat Rev Neurosci*"[Journal] OR '
    '"Nat Rev Cardiol*"[Journal] OR '
    '"Nat Rev Rheumatol*"[Journal] OR '
    '"Nat Rev Gastroenterol Hepatol*"[Journal] OR '
    '"Nat Microbiol*"[Journal] OR '
    '"Nat Neurosci*"[Journal] OR '
    '"Nat Genet*"[Journal] OR '
    '"Nat Metab*"[Journal] OR '
    '"Nat Biomed Eng*"[Journal] OR '
    '"Nat Cancer*"[Journal] OR '
    '"Nat Aging*"[Journal] OR '
    '"Nat Biotechnol*"[Journal] OR '
    '"Nat Methods"[Journal] OR '
    '"Nat Struct Mol Biol*"[Journal] OR '
    '"Nat Chem Biol*"[Journal] OR '
    '"Nat Nanotechnol*"[Journal] OR '
    '"Nat Mater*"[Journal] OR '
    # --- Science 系列 ---
    '"Science"[Journal] OR '
    '"Sci Immunol*"[Journal] OR '
    '"Sci Transl Med*"[Journal] OR '
    '"Sci Adv*"[Journal] OR '
    '"Sci Signal*"[Journal] OR '
    # --- Cell 系列 ---
    '"Cell"[Journal] OR '
    '"Immunity"[Journal] OR '
    '"Cell Host Microbe"[Journal] OR '
    '"Cell Stem Cell"[Journal] OR '
    '"Mol Cell"[Journal] OR '
    '"Cell Metab*"[Journal] OR '
    '"Cancer Cell"[Journal] OR '
    '"Cancer Discov*"[Journal] OR '
    '"Cell Res*"[Journal] OR '
    '"Cell Discov*"[Journal] OR '
    '"Cell Rep Med*"[Journal] OR '
    '"Cell Syst*"[Journal] OR '
    '"Med"[Journal] OR '
    # --- 综合医学顶刊 ---
    '"Lancet"[Journal] OR '
    '"Lancet Respir Med*"[Journal] OR '
    '"Lancet Oncol*"[Journal] OR '
    '"Lancet Infect Dis*"[Journal] OR '
    '"N Engl J Med"[Journal] OR '
    '"JAMA"[Journal] OR '
    '"BMJ"[Journal] OR '
    '"Ann Intern Med"[Journal] OR '
    # --- 生物学/医学1区 ---
    '"J Exp Med*"[Journal] OR '
    '"J Clin Invest*"[Journal] OR '
    '"EMBO J"[Journal] OR '
    '"EMBO Mol Med*"[Journal] OR '
    '"Proc Natl Acad Sci U S A"[Journal] OR '
    '"Blood"[Journal] OR '
    '"Circulation"[Journal] OR '
    '"Annu Rev Immunol*"[Journal] OR '
    '"Annu Rev Med*"[Journal] OR '
    '"Immunol Rev*"[Journal] OR '
    '"Trends Immunol*"[Journal] OR '
    '"Signal Transduct Target Ther"[Journal] OR '
    # --- 呼吸1区 ---
    '"Am J Respir Crit Care Med"[Journal] OR '
    '"Thorax"[Journal] OR '
    '"Eur Respir J"[Journal] OR '
    # --- 材料/递送1区（CAR-M 交叉领域） ---
    '"Adv Mater*"[Journal] OR '
    '"Biomaterials"[Journal] OR '
    '"ACS Nano"[Journal] OR '
    '"J Control Release"[Journal] OR '
    '"Adv Drug Deliv Rev*"[Journal] OR '
    '"Bioact Mater*"[Journal]'
)

RECENT_DAYS = 7
MAX_BACKFILL_DAYS = 90

# ========== 外部服务与邮箱设置 ==========
# 所有账号信息由环境变量注入，避免把邮箱或凭据提交到公开仓库。
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.163.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SMTP_AUTH_CODE = os.environ.get("SMTP_AUTH_CODE", "")
RECEIVER_EMAILS = [
    address.strip()
    for address in os.environ.get("RECEIVER_EMAILS", "").split(",")
    if address.strip()
]

EASYSCHOLAR_KEY = os.environ.get("EASYSCHOLAR_KEY", "")
