/**
 * Cloudflare Email Worker: passes every email sent to leads-…@in.yourdomain.in
 * to our server's email doorbell (/webhooks/email). Free on Cloudflare.
 *
 * Setup (once, after the website is online):
 *  1. Add your domain to Cloudflare. Email → Email Routing → enable it for the
 *     subdomain you chose (INBOUND_EMAIL_DOMAIN, e.g. in.yourdomain.in).
 *  2. Workers & Pages → Create → Worker → paste this file → Deploy.
 *  3. Worker → Settings → Variables: WEBHOOK_URL = https://api.yourdomain.in/webhooks/email
 *                                    INBOUND_KEY = the same value as INBOUND_EMAIL_SECRET in .env (as a Secret)
 *  4. Email Routing → Routing rules → Catch-all → Action "Send to a Worker" → this worker.
 */
export default {
  async email(message, env, ctx) {
    if (message.rawSize > 25 * 1024 * 1024) {
      message.setReject("Message too large");
      return;
    }
    const raw = await new Response(message.raw).arrayBuffer();   // the whole email, exactly as received
    const reply = await fetch(env.WEBHOOK_URL, {
      method: "POST",
      headers: {
        "Content-Type": "message/rfc822",
        "X-Inbound-Key": env.INBOUND_KEY,
        "X-Envelope-To": message.to,
      },
      body: raw,
    });
    if (reply.status >= 500) {
      // Our server had a problem: make the sender's mail server try again later
      throw new Error(`Lead server answered ${reply.status}`);
    }
  },
};
