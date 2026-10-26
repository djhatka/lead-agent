/*
  WhatsApp's "Embedded Signup": Meta's own popup where the owner logs in to
  Facebook and picks their WhatsApp Business number.

  Only used when the backend is set up with real Meta keys (on the live site).
  The popup gives back:
    code             a one-time code the backend swaps for the access key
    waba_id          the owner's WhatsApp Business Account
    phone_number_id  the number they picked
  Everything is then sent to the backend (POST /connections/whatsapp).
*/

let sdk = null

/** Loads Facebook's script once. */
function loadSdk(appId, version) {
  if (sdk) return sdk
  sdk = new Promise((resolve, reject) => {
    window.fbAsyncInit = () => {
      window.FB.init({ appId, autoLogAppEvents: true, xfbml: false, version })
      resolve(window.FB)
    }
    const script = document.createElement('script')
    script.src = 'https://connect.facebook.net/en_US/sdk.js'
    script.async = true
    script.crossOrigin = 'anonymous'
    script.onerror = () => {
      sdk = null
      reject(new Error("Couldn't load Facebook's login window. Check your internet and try again."))
    }
    document.body.appendChild(script)
  })
  return sdk
}

export async function whatsappSignup({ app_id: appId, config_id: configId, graph_version: version }) {
  const FB = await loadSdk(appId, version)
  return new Promise((resolve, reject) => {
    let picked = {}
    // The popup tells us which business account and number were picked.
    const listen = (event) => {
      if (!/(^|\.)facebook\.com$/.test(new URL(event.origin).hostname)) return
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'WA_EMBEDDED_SIGNUP' && data.data?.waba_id)
          picked = { waba_id: data.data.waba_id, phone_number_id: data.data.phone_number_id ?? '' }
      } catch {
        // Some other message from Facebook: not for us.
      }
    }
    window.addEventListener('message', listen)
    FB.login(
      (response) => {
        // The "picked" message can arrive a moment after this answer.
        setTimeout(() => {
          window.removeEventListener('message', listen)
          const code = response.authResponse?.code
          if (code) resolve({ code, ...picked })
          else reject(new Error('The WhatsApp window was closed before finishing.'))
        }, 500)
      },
      {
        config_id: configId,
        response_type: 'code',
        override_default_response_type: true,
        extras: { setup: {}, sessionInfoVersion: '3' },
      },
    )
  })
}
