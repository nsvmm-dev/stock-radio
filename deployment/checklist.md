# Production Release Checklist

## Manual steps (do these BEFORE running switch_to_prod.ps1)

### APIs to upgrade

- [ ] LLM: Get API key from https://console.anthropic.com (Claude Sonnet)
      OR https://platform.openai.com (GPT-4o)
      -> Set in .env.prod: ANTHROPIC_API_KEY or OPENAI_API_KEY

- [ ] J-Quants: Upgrade to paid plan at https://jpx-jquants.com
      -> Get new API key for paid plan
      -> Set in .env.prod: JQUANTS_API_KEY

- [ ] Alpha Vantage: Upgrade to Premium at https://www.alphavantage.co/premium
      -> Same API key, just plan upgrade (no key change needed)
      -> Or switch to Polygon.io: https://polygon.io

### Apple / Firebase (if not done yet)

- [ ] Apple Developer Program ($99/year): https://developer.apple.com
- [ ] APNs key: Certificates > Keys > + > Apple Push Notifications
      -> Download .p8 file (one time only)
- [ ] Firebase: Upload .p8 to Firebase Console > Cloud Messaging
- [ ] Firebase service account key:
      Firebase Console > Project Settings > Service Accounts > Generate new private key
      -> Save as deployment/firebase-credentials-prod.json (gitignored)

### AWS

- [ ] Create prod stack (sam deploy --config-env prod)
- [ ] Upload Firebase credentials to SSM:
      Run: deployment/upload_firebase_prod.ps1

---

## After all manual steps, run:

```powershell
cd c:\02_App\Stock_radio
deployment\switch_to_prod.ps1
```
