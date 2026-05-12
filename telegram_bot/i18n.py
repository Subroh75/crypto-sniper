"""
i18n.py — Multi-language string store for Crypto Sniper bot.
Languages: en, es, vi, id, hi, zh, ar
Falls back to English for any missing key.

Usage:
    from i18n import t
    msg = t("welcome", lang="vi", name="Minh")
"""

_STRINGS: dict[str, dict[str, str]] = {

    # ── Welcome / onboarding ────────────────────────────────────────────────

    "welcome_new": {
        "en": "👋 Hey {name}! Welcome to Crypto Sniper.\n\nI scan 200+ coins in real time using VPRT signals — Volume, Momentum, Range, Trend.\n\nWhat do you want to do first?",
        "es": "👋 ¡Hola {name}! Bienvenido a Crypto Sniper.\n\nEscaneo 200+ monedas en tiempo real con señales VPRT — Volumen, Momentum, Rango, Tendencia.\n\n¿Qué quieres hacer primero?",
        "vi": "👋 Chào {name}! Chào mừng đến với Crypto Sniper.\n\nTôi quét 200+ đồng coin theo thời gian thực bằng tín hiệu VPRT — Khối lượng, Đà, Biên độ, Xu hướng.\n\nBạn muốn làm gì trước?",
        "id": "👋 Hei {name}! Selamat datang di Crypto Sniper.\n\nSaya memindai 200+ koin secara real-time menggunakan sinyal VPRT — Volume, Momentum, Range, Tren.\n\nApa yang ingin kamu lakukan?",
        "hi": "👋 नमस्ते {name}! Crypto Sniper में आपका स्वागत है।\n\nमैं VPRT सिग्नल — वॉल्यूम, मोमेंटम, रेंज, ट्रेंड — का उपयोग करके 200+ कॉइन को रियल टाइम में स्कैन करता हूं।\n\nआप पहले क्या करना चाहते हैं?",
        "zh": "👋 你好 {name}！欢迎来到 Crypto Sniper。\n\n我使用 VPRT 信号（成交量、动能、区间、趋势）实时扫描 200+ 个代币。\n\n你想先做什么？",
        "ar": "👋 مرحباً {name}! أهلاً بك في Crypto Sniper.\n\nأقوم بمسح 200+ عملة في الوقت الفعلي باستخدام إشارات VPRT — الحجم، الزخم، النطاق، الاتجاه.\n\nماذا تريد أن تفعل أولاً؟",
    },

    "welcome_back": {
        "en": "Welcome back, {name}.\n\nAccount: {email} | {tier}\n\nWhat do you need?",
        "es": "Bienvenido de nuevo, {name}.\n\nCuenta: {email} | {tier}\n\n¿En qué puedo ayudarte?",
        "vi": "Chào mừng trở lại, {name}.\n\nTài khoản: {email} | {tier}\n\nBạn cần gì?",
        "id": "Selamat datang kembali, {name}.\n\nAkun: {email} | {tier}\n\nApa yang kamu butuhkan?",
        "hi": "वापसी पर स्वागत है, {name}।\n\nखाता: {email} | {tier}\n\nआपको क्या चाहिए?",
        "zh": "欢迎回来，{name}。\n\n账户：{email} | {tier}\n\n需要什么帮助？",
        "ar": "مرحباً بعودتك، {name}.\n\nالحساب: {email} | {tier}\n\nماذا تحتاج؟",
    },

    # ── About ───────────────────────────────────────────────────────────────

    "about": {
        "en": (
            "CRYPTO SNIPER\n"
            "─────────────────────────\n"
            "Real-time signal engine for crypto traders.\n\n"
            "How it works:\n"
            "Every coin is scored out of 13 using VPRT:\n"
            "  V — Volume spike (up to 5pts)\n"
            "  P — Price momentum (up to 3pts)\n"
            "  R — Range position (up to 2pts)\n"
            "  T — Trend alignment (up to 3pts)\n\n"
            "STRONG BUY = 9+/13 with V + T gates confirmed\n"
            "BUY = V + T + ADX confirmed\n\n"
            "Covers CEX (top 200 coins) + DEX (on-chain gems)\n\n"
            "🌐 https://crypto-sniper.app"
        ),
        "es": (
            "CRYPTO SNIPER\n"
            "─────────────────────────\n"
            "Motor de señales en tiempo real para traders de cripto.\n\n"
            "Cómo funciona:\n"
            "Cada moneda se puntúa sobre 13 usando VPRT:\n"
            "  V — Pico de volumen (hasta 5pts)\n"
            "  P — Momentum de precio (hasta 3pts)\n"
            "  R — Posición en rango (hasta 2pts)\n"
            "  T — Alineación de tendencia (hasta 3pts)\n\n"
            "STRONG BUY = 9+/13 con puertas V + T confirmadas\n\n"
            "🌐 https://crypto-sniper.app"
        ),
        "vi": (
            "CRYPTO SNIPER\n"
            "─────────────────────────\n"
            "Công cụ tín hiệu thời gian thực cho trader crypto.\n\n"
            "Cách hoạt động:\n"
            "Mỗi đồng coin được chấm điểm trên 13 theo VPRT:\n"
            "  V — Đột biến khối lượng (tối đa 5đ)\n"
            "  P — Đà giá (tối đa 3đ)\n"
            "  R — Vị trí biên độ (tối đa 2đ)\n"
            "  T — Căn chỉnh xu hướng (tối đa 3đ)\n\n"
            "STRONG BUY = 9+/13 với V + T đã xác nhận\n\n"
            "🌐 https://crypto-sniper.app"
        ),
        "id": (
            "CRYPTO SNIPER\n"
            "─────────────────────────\n"
            "Mesin sinyal real-time untuk trader kripto.\n\n"
            "Cara kerja:\n"
            "Setiap koin diberi skor dari 13 menggunakan VPRT:\n"
            "  V — Lonjakan volume (hingga 5poin)\n"
            "  P — Momentum harga (hingga 3poin)\n"
            "  R — Posisi range (hingga 2poin)\n"
            "  T — Keselarasan tren (hingga 3poin)\n\n"
            "STRONG BUY = 9+/13 dengan gate V + T terkonfirmasi\n\n"
            "🌐 https://crypto-sniper.app"
        ),
        "hi": (
            "CRYPTO SNIPER\n"
            "─────────────────────────\n"
            "क्रिप्टो ट्रेडर्स के लिए रियल-टाइम सिग्नल इंजन।\n\n"
            "यह कैसे काम करता है:\n"
            "हर कॉइन को VPRT से 13 में से स्कोर किया जाता है:\n"
            "  V — वॉल्यूम स्पाइक (5 अंक तक)\n"
            "  P — प्राइस मोमेंटम (3 अंक तक)\n"
            "  R — रेंज पोजीशन (2 अंक तक)\n"
            "  T — ट्रेंड अलाइनमेंट (3 अंक तक)\n\n"
            "STRONG BUY = 9+/13 जब V + T गेट कन्फर्म\n\n"
            "🌐 https://crypto-sniper.app"
        ),
        "zh": (
            "CRYPTO SNIPER\n"
            "─────────────────────────\n"
            "加密货币交易者的实时信号引擎。\n\n"
            "工作原理：\n"
            "每个代币使用 VPRT 从 13 分满分计分：\n"
            "  V — 成交量爆发（最高5分）\n"
            "  P — 价格动能（最高3分）\n"
            "  R — 区间位置（最高2分）\n"
            "  T — 趋势对齐（最高3分）\n\n"
            "强力买入 = 9+/13，V + T 信号确认\n\n"
            "🌐 https://crypto-sniper.app"
        ),
        "ar": (
            "CRYPTO SNIPER\n"
            "─────────────────────────\n"
            "محرك إشارات فوري لمتداولي العملات المشفرة.\n\n"
            "كيف يعمل:\n"
            "يتم تسجيل كل عملة من أصل 13 باستخدام VPRT:\n"
            "  V — ارتفاع الحجم (حتى 5 نقاط)\n"
            "  P — زخم السعر (حتى 3 نقاط)\n"
            "  R — موضع النطاق (حتى 2 نقطة)\n"
            "  T — محاذاة الاتجاه (حتى 3 نقاط)\n\n"
            "شراء قوي = 9+/13 مع تأكيد بوابتي V + T\n\n"
            "🌐 https://crypto-sniper.app"
        ),
    },

    # ── Help ────────────────────────────────────────────────────────────────

    "help": {
        "en": (
            "CRYPTO SNIPER — COMMANDS\n"
            "─────────────────────────\n"
            "SIGNALS\n"
            "/analyse BTC       — CEX signal (default 1H)\n"
            "/analyse BTC 4H    — specify interval\n"
            "/gem <address>     — DEX token deep scan\n"
            "/gems              — latest hourly DEX sweep\n\n"
            "TRACKER\n"
            "/record            — win rate & signal history\n"
            "/record cex        — CEX only\n"
            "/record dex        — DEX only\n\n"
            "WATCHLIST\n"
            "/watch <address>   — watch a DEX token\n"
            "/unwatch <address> — stop watching\n"
            "/mywatches         — your watchlist\n"
            "/chains            — active DEX chains\n\n"
            "ACCOUNT\n"
            "/status            — your tier & usage\n"
            "/link              — link your email\n\n"
            "Or just type a question — I'll answer it.\n"
            "🌐 https://crypto-sniper.app"
        ),
        "es": (
            "CRYPTO SNIPER — COMANDOS\n"
            "─────────────────────────\n"
            "SEÑALES\n"
            "/analyse BTC       — señal CEX (1H por defecto)\n"
            "/analyse BTC 4H    — especificar intervalo\n"
            "/gem <dirección>   — escaneo DEX profundo\n"
            "/gems              — último barrido DEX\n\n"
            "RASTREADOR\n"
            "/record            — tasa de aciertos e historial\n"
            "/record cex        — solo CEX\n"
            "/record dex        — solo DEX\n\n"
            "LISTA DE SEGUIMIENTO\n"
            "/watch <dirección>   — seguir token DEX\n"
            "/unwatch <dirección> — dejar de seguir\n"
            "/mywatches           — mi lista\n\n"
            "CUENTA\n"
            "/status  — tu nivel y uso\n"
            "/link    — vincular email\n\n"
            "🌐 https://crypto-sniper.app"
        ),
        "vi": (
            "CRYPTO SNIPER — LỆNH\n"
            "─────────────────────────\n"
            "TÍN HIỆU\n"
            "/analyse BTC       — tín hiệu CEX (mặc định 1H)\n"
            "/analyse BTC 4H    — chỉ định khung thời gian\n"
            "/gem <địa chỉ>     — quét sâu token DEX\n"
            "/gems              — kết quả quét DEX mới nhất\n\n"
            "THEO DÕI\n"
            "/record            — tỉ lệ thắng & lịch sử tín hiệu\n"
            "/record cex        — chỉ CEX\n"
            "/record dex        — chỉ DEX\n\n"
            "DANH SÁCH THEO DÕI\n"
            "/watch <địa chỉ>   — theo dõi token DEX\n"
            "/unwatch <địa chỉ> — bỏ theo dõi\n"
            "/mywatches         — danh sách của bạn\n\n"
            "TÀI KHOẢN\n"
            "/status  — gói & mức sử dụng\n"
            "/link    — liên kết email\n\n"
            "🌐 https://crypto-sniper.app"
        ),
        "id": (
            "CRYPTO SNIPER — PERINTAH\n"
            "─────────────────────────\n"
            "SINYAL\n"
            "/analyse BTC       — sinyal CEX (default 1H)\n"
            "/analyse BTC 4H    — tentukan interval\n"
            "/gem <alamat>      — scan mendalam token DEX\n"
            "/gems              — hasil sweep DEX terbaru\n\n"
            "PELACAK\n"
            "/record            — win rate & riwayat sinyal\n"
            "/record cex        — hanya CEX\n"
            "/record dex        — hanya DEX\n\n"
            "WATCHLIST\n"
            "/watch <alamat>    — pantau token DEX\n"
            "/unwatch <alamat>  — berhenti pantau\n"
            "/mywatches         — daftar pantauanmu\n\n"
            "AKUN\n"
            "/status  — tier & penggunaan\n"
            "/link    — hubungkan email\n\n"
            "🌐 https://crypto-sniper.app"
        ),
        "hi": (
            "CRYPTO SNIPER — कमांड\n"
            "─────────────────────────\n"
            "सिग्नल\n"
            "/analyse BTC       — CEX सिग्नल (डिफ़ॉल्ट 1H)\n"
            "/analyse BTC 4H    — इंटरवल चुनें\n"
            "/gem <एड्रेस>      — DEX टोकन डीप स्कैन\n"
            "/gems              — ताज़ा DEX स्वीप\n\n"
            "ट्रैकर\n"
            "/record            — जीत दर और सिग्नल इतिहास\n"
            "/record cex        — केवल CEX\n"
            "/record dex        — केवल DEX\n\n"
            "वॉचलिस्ट\n"
            "/watch <एड्रेस>    — DEX टोकन फॉलो करें\n"
            "/unwatch <एड्रेस>  — फॉलो बंद करें\n"
            "/mywatches         — आपकी लिस्ट\n\n"
            "खाता\n"
            "/status  — टियर और उपयोग\n"
            "/link    — ईमेल लिंक करें\n\n"
            "🌐 https://crypto-sniper.app"
        ),
        "zh": (
            "CRYPTO SNIPER — 命令列表\n"
            "─────────────────────────\n"
            "信号\n"
            "/analyse BTC       — CEX信号（默认1H）\n"
            "/analyse BTC 4H    — 指定时间框架\n"
            "/gem <地址>         — DEX代币深度扫描\n"
            "/gems              — 最新DEX扫描结果\n\n"
            "追踪器\n"
            "/record            — 胜率与信号历史\n"
            "/record cex        — 仅CEX\n"
            "/record dex        — 仅DEX\n\n"
            "监控列表\n"
            "/watch <地址>      — 监控DEX代币\n"
            "/unwatch <地址>    — 取消监控\n"
            "/mywatches         — 我的监控列表\n\n"
            "账户\n"
            "/status  — 等级与使用情况\n"
            "/link    — 绑定邮箱\n\n"
            "🌐 https://crypto-sniper.app"
        ),
        "ar": (
            "CRYPTO SNIPER — الأوامر\n"
            "─────────────────────────\n"
            "الإشارات\n"
            "/analyse BTC       — إشارة CEX (1H افتراضي)\n"
            "/analyse BTC 4H    — تحديد الإطار الزمني\n"
            "/gem <العنوان>     — مسح عميق لرمز DEX\n"
            "/gems              — أحدث نتائج المسح\n\n"
            "المتتبع\n"
            "/record            — معدل الفوز وسجل الإشارات\n"
            "/record cex        — CEX فقط\n"
            "/record dex        — DEX فقط\n\n"
            "قائمة المراقبة\n"
            "/watch <العنوان>   — مراقبة رمز DEX\n"
            "/unwatch <العنوان> — إيقاف المراقبة\n"
            "/mywatches         — قائمتك\n\n"
            "الحساب\n"
            "/status  — مستواك واستخدامك\n"
            "/link    — ربط البريد الإلكتروني\n\n"
            "🌐 https://crypto-sniper.app"
        ),
    },

    # ── Prompt to enter a symbol ─────────────────────────────────────────────

    "enter_symbol": {
        "en": "Which coin? Reply with the symbol.\nExample: BTC  or  ETH  or  SOL\n\nAdd an interval after it: BTC 4H",
        "es": "¿Qué moneda? Responde con el símbolo.\nEjemplo: BTC  o  ETH  o  SOL\n\nAgrega un intervalo: BTC 4H",
        "vi": "Coin nào? Nhập ký hiệu coin.\nVí dụ: BTC  hoặc  ETH  hoặc  SOL\n\nThêm khung giờ nếu muốn: BTC 4H",
        "id": "Koin apa? Balas dengan simbol.\nContoh: BTC  atau  ETH  atau  SOL\n\nTambahkan interval: BTC 4H",
        "hi": "कौन सा कॉइन? सिंबल टाइप करें।\nउदाहरण: BTC या ETH या SOL\n\nइंटरवल भी दे सकते हैं: BTC 4H",
        "zh": "哪个代币？请输入符号。\n例如：BTC 或 ETH 或 SOL\n\n可加时间框架：BTC 4H",
        "ar": "أي عملة؟ أرسل الرمز.\nمثال: BTC أو ETH أو SOL\n\nأضف إطاراً زمنياً: BTC 4H",
    },

    "enter_dex_address": {
        "en": "Send me the contract address or token name.\nExample: 0xTokenAddress  or  PEPE\n\nOptionally add chain: 0x... bsc",
        "es": "Envíame la dirección del contrato o nombre del token.\nEjemplo: 0xDireccion  o  PEPE",
        "vi": "Gửi địa chỉ hợp đồng hoặc tên token.\nVí dụ: 0xDiaChiToken  hoặc  PEPE",
        "id": "Kirim alamat kontrak atau nama token.\nContoh: 0xAlamatToken  atau  PEPE",
        "hi": "कॉन्ट्रैक्ट एड्रेस या टोकन का नाम भेजें।\nउदाहरण: 0xTokenAddress या PEPE",
        "zh": "发送合约地址或代币名称。\n例如：0x代币地址 或 PEPE",
        "ar": "أرسل عنوان العقد أو اسم الرمز.\nمثال: 0xعنوانالعقد أو PEPE",
    },

    # ── Rate limit ───────────────────────────────────────────────────────────

    "rate_limit": {
        "en": "You've used your {limit} free DEX scans for today.\n\nLimit resets at midnight UTC.\n\nUpgrade for unlimited scans:\nhttps://crypto-sniper.app",
        "es": "Usaste tus {limit} escaneos DEX gratuitos de hoy.\n\nSe reinicia a medianoche UTC.\n\nActualiza para escaneos ilimitados:\nhttps://crypto-sniper.app",
        "vi": "Bạn đã dùng hết {limit} lần quét DEX miễn phí hôm nay.\n\nGiới hạn đặt lại lúc nửa đêm UTC.\n\nNâng cấp để quét không giới hạn:\nhttps://crypto-sniper.app",
        "id": "Kamu sudah menggunakan {limit} scan DEX gratis hari ini.\n\nBatas direset tengah malam UTC.\n\nUpgrade untuk scan tak terbatas:\nhttps://crypto-sniper.app",
        "hi": "आपने आज के {limit} मुफ्त DEX स्कैन उपयोग कर लिए।\n\nमध्यरात्रि UTC पर रीसेट होगा।\n\nअनलिमिटेड स्कैन के लिए अपग्रेड करें:\nhttps://crypto-sniper.app",
        "zh": "你今天的 {limit} 次免费DEX扫描已用完。\n\n限制在UTC午夜重置。\n\n升级获得无限扫描：\nhttps://crypto-sniper.app",
        "ar": "لقد استخدمت عمليات المسح المجانية الـ {limit} اليوم.\n\nيُعاد التعيين عند منتصف الليل UTC.\n\nقم بالترقية للحصول على عمليات مسح غير محدودة:\nhttps://crypto-sniper.app",
    },
}

# Supported language codes (Telegram language_code values)
SUPPORTED_LANGS = {"en", "es", "vi", "id", "hi", "zh", "ar"}
_LANG_MAP = {
    "zh-hans": "zh", "zh-hant": "zh", "zh-cn": "zh", "zh-tw": "zh",
    "es-419": "es",
}


def resolve_lang(code: str | None) -> str:
    """Normalise a Telegram language_code to one of our supported keys."""
    if not code:
        return "en"
    code = code.lower().strip()
    if code in SUPPORTED_LANGS:
        return code
    if code in _LANG_MAP:
        return _LANG_MAP[code]
    # Try prefix match — e.g. "vi-vn" -> "vi"
    prefix = code.split("-")[0]
    return prefix if prefix in SUPPORTED_LANGS else "en"


def t(key: str, lang: str = "en", **kwargs) -> str:
    """
    Get a translated string by key.
    Falls back to English if key or lang not found.
    Supports str.format(**kwargs) substitution.
    """
    bucket = _STRINGS.get(key, {})
    text = bucket.get(lang) or bucket.get("en") or f"[missing:{key}]"
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass
    return text
