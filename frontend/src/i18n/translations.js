/*
  Task 39: one switch, every screen in Hindi.

  A flat dictionary: { key: { en: "...", hi: "..." } }. t(key) below looks
  up the current language and falls back to English (then to the key
  itself) if a translation is ever missing, so a half-translated screen
  never shows a blank.

  Keeping this in one file - instead of scattering strings across every
  page - is what makes "one switch" possible: add a language here once,
  and it's wired everywhere t() is already used.
*/

export const DICTIONARY = {
  // ---- Brand / chrome -------------------------------------------------
  'app.tagline': { en: 'Your AI team', hi: 'आपकी AI टीम' },
  'common.logout': { en: 'Log out', hi: 'लॉग आउट' },
  'common.more': { en: 'More', hi: 'और' },
  'common.close': { en: 'Close', hi: 'बंद करें' },
  'common.theme': { en: 'Theme', hi: 'थीम' },
  'common.language': { en: 'Language', hi: 'भाषा' },
  'common.skipToContent': { en: 'Skip to content', hi: 'सामग्री पर जाएँ' },
  'common.cantReachServer': { en: "Can't reach your dashboard's server", hi: 'आपके डैशबोर्ड का सर्वर नहीं मिल रहा' },
  'common.couldntLoad': { en: "Couldn't load this", hi: 'यह लोड नहीं हो सका' },
  'common.somethingWrong': { en: 'Something went wrong.', hi: 'कुछ गड़बड़ हो गई।' },
  'common.tryAgain': { en: 'Try again', hi: 'फिर कोशिश करें' },
  'common.loading': { en: 'Loading', hi: 'लोड हो रहा है' },
  'common.save': { en: 'Save', hi: 'सेव करें' },
  'common.saved': { en: 'Saved', hi: 'सेव हो गया' },
  'common.cancel': { en: 'Cancel', hi: 'रद्द करें' },
  'common.saving': { en: 'Saving…', hi: 'सेव हो रहा है…' },
  'common.lastNDays': { en: 'Last {n} days', hi: 'पिछले {n} दिन' },
  'common.nDays': { en: '{n} days', hi: '{n} दिन' },

  // ---- Theme toggle -----------------------------------------------------
  'theme.label': { en: 'Colour theme', hi: 'रंग थीम' },
  'theme.light': { en: 'Light', hi: 'हल्का' },
  'theme.system': { en: 'System', hi: 'सिस्टम' },
  'theme.dark': { en: 'Dark', hi: 'गहरा' },

  // ---- Language toggle ----------------------------------------------------
  'language.english': { en: 'English', hi: 'English' },
  'language.hindi': { en: 'Hindi', hi: 'हिंदी' },

  // ---- Status footer / pills --------------------------------------------
  'status.server': { en: 'Server', hi: 'सर्वर' },
  'status.ai': { en: 'AI', hi: 'AI' },
  'status.newEnquiries': { en: 'New enquiries', hi: 'नई पूछताछ' },
  'status.unreachable': { en: 'Unreachable', hi: 'नहीं मिल रहा' },
  'status.online': { en: 'Online', hi: 'ऑनलाइन' },
  'status.checking': { en: 'Checking…', hi: 'जाँच हो रही है…' },
  'status.claude': { en: 'Claude', hi: 'Claude' },
  'status.practice': { en: 'Practice', hi: 'अभ्यास' },
  'status.live': { en: 'Live', hi: 'लाइव' },
  'status.connecting': { en: 'Connecting…', hi: 'कनेक्ट हो रहा है…' },
  'status.every30s': { en: 'Every 30 s', hi: 'हर 30 सेकंड' },
  'status.sampleData': { en: 'Sample data', hi: 'नमूना डेटा' },
  'status.practiceAi': { en: 'Practice AI', hi: 'अभ्यास AI' },

  // ---- Nav: top-level items ----------------------------------------------
  'nav.home': { en: 'Home', hi: 'होम' },
  'nav.leads': { en: 'Enquiries', hi: 'पूछताछ' },
  'nav.payments': { en: 'Payments', hi: 'भुगतान' },
  'nav.billing': { en: 'Plan & billing', hi: 'प्लान और बिल' },
  'route.billing.title': { en: 'Plan & billing', hi: 'प्लान और बिल' },
  'route.billing.subtitle': { en: 'Your plan, what it includes, and how to pay', hi: 'आपका प्लान, उसमें क्या है, और भुगतान कैसे करें' },
  'nav.renewals': { en: 'Renewals', hi: 'नवीनीकरण' },
  'nav.sources': { en: 'Where customers come from', hi: 'ग्राहक कहाँ से आते हैं' },
  'nav.sources.short': { en: 'Sources', hi: 'स्रोत' },
  'nav.content': { en: 'Content calendar', hi: 'कंटेंट कैलेंडर' },
  'nav.content.short': { en: 'Content', hi: 'कंटेंट' },
  'nav.contentPerformance': { en: "What's working", hi: 'क्या काम कर रहा है' },
  'nav.results': { en: 'Your results', hi: 'आपके नतीजे' },
  'nav.results.short': { en: 'Results', hi: 'नतीजे' },
  'nav.weeklyReview': { en: 'Weekly review', hi: 'साप्ताहिक समीक्षा' },
  'nav.reviews': { en: 'Reviews', hi: 'रिव्यू' },
  'nav.aiTeam': { en: 'AI team', hi: 'AI टीम' },
  'nav.connections': { en: 'Connected apps', hi: 'जुड़े हुए ऐप्स' },
  'nav.connections.short': { en: 'Apps', hi: 'ऐप्स' },
  'nav.settings': { en: 'Settings', hi: 'सेटिंग्स' },
  'nav.group.socialMedia': { en: 'Social media', hi: 'सोशल मीडिया' },
  'nav.group.growth': { en: 'Growth', hi: 'ग्रोथ' },
  'nav.group.behindScenes': { en: 'Behind the scenes', hi: 'पर्दे के पीछे' },

  // ---- Page headers (title + subtitle, read from routes.jsx) -----------
  'route.leads.title': { en: 'Enquiries', hi: 'पूछताछ' },
  'route.leads.subtitle': { en: 'Every enquiry from every channel, scored by the AI', hi: 'हर चैनल से आई हर पूछताछ, AI द्वारा स्कोर की गई' },
  'route.sources.title': { en: 'Where customers come from', hi: 'ग्राहक कहाँ से आते हैं' },
  'route.sources.subtitle': { en: 'Which channels bring enquiries, and which bring money', hi: 'कौन-से चैनल पूछताछ लाते हैं, और कौन-से पैसे' },
  'route.payments.title': { en: 'Payments', hi: 'भुगतान' },
  'route.payments.subtitle': {
    en: 'Advances, fees and dues, paid straight to your UPI. Polite reminders included.',
    hi: 'एडवांस, फीस और बकाया, सीधे आपके UPI में। साथ में शालीन रिमाइंडर भी।',
  },
  'route.renewals.title': { en: 'Renewals', hi: 'नवीनीकरण' },
  'route.renewals.subtitle': {
    en: 'Memberships and services about to expire. A ready message for each, so nobody lapses.',
    hi: 'सदस्यता और सेवाएँ जो जल्द खत्म होने वाली हैं। हर एक के लिए तैयार मैसेज, ताकि कोई छूटे नहीं।',
  },
  'route.content.title': { en: 'Content calendar', hi: 'कंटेंट कैलेंडर' },
  'route.content.subtitle': {
    en: 'Your next 7 days of posts. Nothing goes out until you schedule it.',
    hi: 'अगले 7 दिनों की पोस्ट। जब तक आप शेड्यूल न करें, कुछ भी पब्लिश नहीं होता।',
  },
  'route.contentPerformance.title': { en: "What's working", hi: 'क्या काम कर रहा है' },
  'route.contentPerformance.subtitle': {
    en: 'Which posts bring customers and ₹, not just likes',
    hi: 'कौन-सी पोस्ट ग्राहक और ₹ लाती हैं, सिर्फ लाइक नहीं',
  },
  'route.results.title': { en: 'Your results', hi: 'आपके नतीजे' },
  'route.results.subtitle': {
    en: 'What Lead Intel did for you, month by month, in customers and ₹',
    hi: 'Lead Intel ने हर महीने आपके लिए क्या किया, ग्राहकों और ₹ में',
  },
  'route.weeklyReview.title': { en: 'Weekly review', hi: 'साप्ताहिक समीक्षा' },
  'route.weeklyReview.subtitle': {
    en: 'What happened, what is missing, and your 3 actions',
    hi: 'क्या हुआ, क्या कमी है, और आपके 3 काम',
  },
  'route.reviews.title': { en: 'Reviews', hi: 'रिव्यू' },
  'route.reviews.subtitle': {
    en: 'Your Google rating, AI-drafted replies and review requests',
    hi: 'आपकी Google रेटिंग, AI के बनाए जवाब और रिव्यू के अनुरोध',
  },
  'route.aiTeam.title': { en: 'AI team', hi: 'AI टीम' },
  'route.aiTeam.subtitle': { en: 'What each AI helper did, step by step, and why', hi: 'हर AI सहायक ने क्या किया, कदम-दर-कदम, और क्यों' },
  'route.connections.title': { en: 'Connected apps', hi: 'जुड़े हुए ऐप्स' },
  'route.connections.subtitle': {
    en: 'Link your Instagram, Facebook, WhatsApp and Google so the AI can work with them',
    hi: 'अपना Instagram, Facebook, WhatsApp और Google जोड़ें ताकि AI उनके साथ काम कर सके',
  },
  'route.settings.title': { en: 'Settings', hi: 'सेटिंग्स' },
  'route.settings.subtitle': {
    en: 'Your business details (the AI writes from these) and social accounts',
    hi: 'आपके बिज़नेस की जानकारी (AI इसी से लिखता है) और सोशल अकाउंट',
  },

  // ---- Settings page: language section ----------------------------------
  'settings.language.title': { en: 'Dashboard language', hi: 'डैशबोर्ड की भाषा' },
  'status.aboutSampleData': { en: 'About the sample data', hi: 'नमूना डेटा के बारे में' },
  'status.someSampleData': { en: 'Some of this page is sample data', hi: 'इस पेज का कुछ हिस्सा नमूना डेटा है' },
  'status.sampleDataEverything': {
    en: "This business isn't on the server yet, so everything you see here is built-in sample data.",
    hi: 'यह बिज़नेस अभी सर्वर पर नहीं है, इसलिए यहाँ जो भी दिख रहा है वह बिल्ट-इन नमूना डेटा है।',
  },
  'status.sampleDataPartial': {
    en: "The server doesn't have {areas} yet, so that part shows built-in sample data.",
    hi: 'सर्वर पर अभी {areas} नहीं है, इसलिए वह हिस्सा बिल्ट-इन नमूना डेटा दिखाता है।',
  },
  'status.sampleDataFooter': {
    en: "Changes you make to sample data aren't sent anywhere and reset when you reload the page.",
    hi: 'नमूना डेटा में किए बदलाव कहीं नहीं भेजे जाते और पेज रीलोड करने पर रीसेट हो जाते हैं।',
  },
  'status.aboutPracticeAi': { en: 'About practice AI', hi: 'अभ्यास AI के बारे में' },
  'status.practiceAiHeading': { en: 'The AI is in free practice mode', hi: 'AI अभी मुफ्त अभ्यास मोड में है' },
  'status.practiceAiBody': {
    en: 'Scores, drafts and reviews come from simple built-in rules instead of Claude, so they cost nothing. They still show you how everything works.',
    hi: 'स्कोर, ड्राफ्ट और रिव्यू Claude की बजाय साधारण बिल्ट-इन नियमों से आते हैं, इसलिए इनका कोई खर्च नहीं। फिर भी ये दिखाते हैं कि सब कैसे काम करता है।',
  },
  'status.practiceAiFooter': {
    en: "To switch to Claude, set MOCK_AI=false and an API key in the server's .env.",
    hi: 'Claude पर जाने के लिए, सर्वर की .env फ़ाइल में MOCK_AI=false और एक API key सेट करें।',
  },
  'toast.newHotEnquiry': { en: 'New hot enquiry', hi: 'नई हॉट पूछताछ' },
  'toast.someone': { en: 'Someone', hi: 'कोई' },
  'toast.openEnquiry': { en: 'Open enquiry', hi: 'पूछताछ खोलें' },
  'toast.confirmIt': { en: 'Confirm it', hi: 'पुष्टि करें' },
  // ---- Home page ---------------------------------------------------------
  'home.subtitle': { en: "here's how {name} is doing", hi: '{name} कैसा कर रहा है' },
  'home.stat.enquiries': { en: 'Enquiries', hi: 'पूछताछ' },
  'home.stat.sales': { en: 'Sales', hi: 'बिक्री' },
  'home.stat.revenue': { en: 'Revenue', hi: 'कमाई' },
  'home.stat.replyTime': { en: 'Typical reply time', hi: 'औसत जवाब समय' },
  'home.stat.vsDaysBefore': { en: 'vs the {n} days before', hi: 'पिछले {n} दिनों की तुलना में' },
  'home.stat.boughtPct': { en: '{pct}% of enquiries bought', hi: '{pct}% पूछताछ ने खरीदा' },
  'home.stat.avgSale': { en: 'avg sale {amount}', hi: 'औसत बिक्री {amount}' },
  'home.stat.repliedWithin5min': { en: '{pct}% answered within 5 min', hi: '{pct}% को 5 मिनट में जवाब मिला' },
  'home.callFirst': { en: 'Call these first', hi: 'इन्हें पहले कॉल करें' },
  'home.hotEnquiriesSubtitle': { en: 'Hot enquiries, most likely to buy at the top', hi: 'हॉट पूछताछ, खरीदने की सबसे ज़्यादा संभावना वालीं सबसे ऊपर' },
  'home.all': { en: 'All {n}', hi: 'सभी {n}' },
  'home.noHotEnquiries': { en: 'No hot enquiries right now', hi: 'अभी कोई हॉट पूछताछ नहीं' },
  'home.noHotEnquiriesBody': { en: 'New ones pop up here the moment the AI flags them.', hi: 'AI के पहचानते ही नई पूछताछ यहाँ दिख जाएगी।' },
  'home.followUpToday': { en: 'Follow up today', hi: 'आज फॉलो-अप करें' },
  'home.followUpSubtitle': {
    en: 'Enquiries that went quiet for {days} day{plural} or more. Most sales are won on the follow-up.',
    hi: '{days} दिन{plural} या उससे ज़्यादा से चुप पूछताछ। ज़्यादातर बिक्री फॉलो-अप पर ही होती है।',
  },
  'home.showFewer': { en: 'Show fewer', hi: 'कम दिखाएँ' },
  'home.allCaughtUp': { en: 'All caught up. Nobody is waiting for a follow-up.', hi: 'सब हो गया। किसी को फॉलो-अप का इंतज़ार नहीं है।' },
  'home.followUp': { en: 'Follow up', hi: 'फॉलो-अप' },
  'home.renewals': { en: 'Renewals', hi: 'नवीनीकरण' },
  'home.renewalsSubtitle': { en: 'Memberships or services expiring within {days} days', hi: '{days} दिनों में खत्म हो रही सदस्यता या सेवाएँ' },
  'home.viewAll': { en: 'View all', hi: 'सभी देखें' },
  'home.renew': { en: 'Renew', hi: 'नवीनीकरण करें' },
  'home.whatHappened': { en: 'What happened', hi: 'क्या हुआ' },
  'home.lastNDaysPlainWords': { en: 'The last {n} days in plain words', hi: 'पिछले {n} दिन, आसान शब्दों में' },
  'home.nothingToReport': { en: 'Nothing to report yet. Highlights appear once enquiries come in.', hi: 'अभी कुछ नहीं है। पूछताछ आने पर हाइलाइट्स दिखेंगे।' },
  'home.threeActions': { en: "This week's 3 actions", hi: 'इस हफ्ते के 3 काम' },
  'home.fromWeeklyReview': { en: 'From your weekly review of {date}', hi: '{date} की आपकी साप्ताहिक समीक्षा से' },
  'home.fromWeeklyReviewPlain': { en: 'From your weekly review', hi: 'आपकी साप्ताहिक समीक्षा से' },
  'home.fullReview': { en: 'Full review', hi: 'पूरी समीक्षा' },
  'home.noWeeklyReview': { en: 'No weekly review yet', hi: 'अभी कोई साप्ताहिक समीक्षा नहीं' },
  'home.runFirstReview': { en: 'Run your first review', hi: 'अपनी पहली समीक्षा चलाएँ' },
  'home.weeklyReviewBody': {
    en: 'The AI looks at your week and picks the 3 things that will bring the most customers.',
    hi: 'AI आपके हफ्ते को देखकर 3 ऐसे काम चुनता है जो सबसे ज़्यादा ग्राहक लाएँगे।',
  },
  'home.doItNow': { en: 'Do it now', hi: 'अभी करें' },
  'settings.language.subtitle': {
    en: 'One switch, every screen - the menu, page titles and your business details.',
    hi: 'एक ही स्विच, हर स्क्रीन पर - मेनू, पेज के टाइटल और आपके बिज़नेस की जानकारी।',
  },
}

export const LANGUAGES = [
  { value: 'en', labelKey: 'language.english' },
  { value: 'hi', labelKey: 'language.hindi' },
]

/** Looks up `key` in `lang` ("en" | "hi"), falling back to English, then the raw key.
    `vars` does simple {{n}}-less {n} replacement, e.g. t('common.nDays', { n: 7 }). */
export function translate(lang, key, vars) {
  const entry = DICTIONARY[key]
  let text = entry ? (entry[lang] ?? entry.en) : key
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.replaceAll(`{${name}}`, value)
    }
  }
  return text
}
