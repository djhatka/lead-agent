/*
  The three demo businesses: who they are, what they sell, and the words
  their customers, reviewers and the AI use. src/api/sample/world.js turns
  this into months of enquiries, posts and reviews.

  Only used when the server doesn't have a part of the API yet.
*/

export const PROFILES = [
  {
    business: {
      id: 1,
      name: 'Pulse Fitness Studio',
      category: 'gym',
      category_label: 'Gym & fitness studio',
      city: 'Pune',
      area: 'Baner',
      phone: '9000011111',
      brand_voice: 'Warm, energetic and encouraging. Hinglish is fine. Never shame anyone about their body.',
      target_audience: 'Working professionals aged 22–40 in Baner and Aundh who want to get fit before or after office.',
      google_review_link: 'https://g.page/r/pulse-fitness-baner/review',
      opening_hours: '5:30 am – 10:30 pm',
    },
    services: [
      { key: 'monthly', name: 'Monthly membership', price: [2500, 2500], weight: 26 },
      { key: 'quarterly', name: 'Quarterly membership', price: [6500, 6500], weight: 18 },
      { key: 'annual', name: 'Annual membership', price: [18000, 21000], weight: 8 },
      { key: 'personal_training', name: 'Personal training', price: [9000, 14000], weight: 14 },
      { key: 'yoga', name: 'Yoga batch', price: [2000, 2200], weight: 12 },
      { key: 'zumba', name: 'Zumba batch', price: [1800, 1800], weight: 9 },
      { key: 'trial', name: 'Free trial', price: [0, 0], weight: 13 },
    ],
    sources: { instagram: 34, google: 16, whatsapp: 16, walkin: 9, website: 8, justdial: 17 },
    // Share of each channel's enquiries that turn into customers (before reply speed and tone).
    win: { instagram: 0.13, google: 0.42, whatsapp: 0.33, walkin: 0.55, website: 0.3, justdial: 0.18 },
    // Enquiries by hour, India time: gyms peak before and after office.
    hours: [0, 0, 0, 0, 0, 1, 5, 7, 6, 4, 3, 3, 3, 2, 2, 2, 3, 5, 8, 9, 8, 6, 3, 1],
    messages: {
      monthly: [
        'Hi, monthly membership ka kya fees hai? Morning 6 baje ka batch chahiye',
        'What are your monthly charges? Is there a joining fee?',
        'Bhai gym join karna hai, monthly kitna lagega?',
      ],
      quarterly: [
        'What is the price for 3 months? I stay in Baner, can join from Monday',
        'Quarterly plan pe koi offer chal raha hai Diwali ka?',
      ],
      annual: ['Annual membership ka best price batao, 2 log hain (couple)', 'Do you have an annual plan with locker included?'],
      personal_training: [
        'Personal trainer chahiye weight loss ke liye, 15 kg kam karna hai. Rates?',
        'Need a PT for 3 months, wedding in February. Can we start this week?',
        'Is there a female trainer for personal training?',
      ],
      yoga: ['Do you have a ladies yoga batch in the evening?', 'Yoga classes timing kya hai? Back pain ke liye karna hai'],
      zumba: ['Zumba classes timing? Me and my sister want to join', 'Zumba weekend batch hai kya?'],
      trial: ['Free trial milega kya? Kal aana chahta hoon', 'Can I come for a trial session tomorrow morning?'],
    },
    urgent: ['Need to start today itself, please call me', 'Kal se join karna hai, abhi call karo please'],
    frustrated: [
      'Called twice yesterday, nobody picked up. Do you even reply? Still want to join this week.',
      'Sent a message 2 days back, no reply. Is the gym open?',
    ],
    followups: ['Ok, kal subah 6:30 aata hoon trial ke liye', 'Thoda discount ho sakta hai?', 'Location bhej do please', 'Done, joining Monday. Thanks!'],
    replies: [
      'Hi {name}! {service} is ₹{price}. Come for a free trial session anytime 6–10 am or 5–9 pm 💪',
      'Hello {name}, thanks for reaching out! {service} is ₹{price}. Shall I book a trial slot for you?',
    ],
    reviews: {
      good: [
        ['Great trainers, especially Rahul sir. The morning crowd is super motivating.', ['Trainers', 'Atmosphere']],
        ['Lost 9 kg in 4 months with personal training. They actually track your diet.', ['Personal training', 'Results']],
        ['Very clean, equipment is new and well maintained. Worth the money.', ['Cleanliness', 'Equipment']],
        ['Best yoga batch in Baner. Instructor corrects every posture patiently.', ['Yoga batch', 'Trainers']],
        ['Zumba on Saturdays is the highlight of my week! Fun people.', ['Zumba', 'Atmosphere']],
        ['Flexible timings and staff always help. Locker rooms are clean.', ['Timings', 'Cleanliness']],
      ],
      ok: [['Good gym but gets crowded after 7 pm. Equipment is good.', ['Equipment'], ['Crowded evenings']]],
      bad: [
        ['AC does not work properly in the evening and showers are always wet. Expected better for the price.', ['AC', 'Washrooms']],
        ['Asked for a refund for the unused months after shifting cities, nobody responded.', ['Refunds', 'Slow replies']],
        ['Trainer was on the phone half the session. Not worth personal training fees.', ['Trainer attention']],
        ['Parking is a nightmare in the evening and the staff do not help.', ['Parking']],
      ],
    },
    ideas: [
      {
        pillar: 'offer', platform: 'instagram', format: 'reel', hour: 19,
        title: 'Diwali offer: 3 months + 1 month free',
        caption: 'Diwali pe naya YOU 🪔 Join any 3-month plan this week and get 1 month FREE. Only till Sunday!\n\nDM "DIWALI" or WhatsApp us to book a free trial.',
        hashtags: ['#PuneGym', '#BanerFitness', '#DiwaliOffer', '#FitnessMotivation', '#PulseFitness'],
        script: 'Hook (0–2s): "Diwali sweets ka guilt? We got you."\nMiddle: quick cuts of members training, trainer high-fives.\nOffer card: "3 months + 1 FREE".\nCTA: "DM DIWALI to book your free trial."',
        shots: ['Close-up of diya on the reception desk', 'Member deadlifting, slow motion', 'Trainer high-five', 'Offer text over the gym floor', 'Owner pointing at the camera for the CTA'],
      },
      {
        pillar: 'testimonial', platform: 'instagram', format: 'reel', hour: 19,
        title: "Member story: Priya's 12 kg in 4 months",
        caption: '12 kg down. 4 months. Zero crash diets. 🙌\nPriya started with 3 sessions a week and a simple Indian diet plan from our coach.\n\nYour turn? Free trial this week. Link in bio.',
        hashtags: ['#TransformationTuesday', '#WeightLossJourney', '#PuneGym', '#PulseFitness'],
        script: 'Hook: before/after photo flip.\nPriya (talking to camera): "I was scared of the gym. Day 1 they made a plan just for me."\nShow her workout + diet plan.\nCTA: "Start your story: free trial this week."',
        shots: ['Before/after side by side (with consent)', 'Priya talking to camera at the entrance', 'Her squat set with coach', 'Diet plan on a phone screen'],
      },
      {
        pillar: 'educational', platform: 'instagram', format: 'carousel', hour: 8,
        title: '5 mistakes beginners make on day 1',
        caption: 'New to the gym? Avoid these 5 mistakes 👇\n1. Skipping warm-up\n2. Copying advanced routines\n3. Lifting too heavy\n4. No water\n5. Giving up in week 2\n\nSave this for your first day!',
        hashtags: ['#GymTips', '#BeginnerWorkout', '#FitnessIndia', '#PuneGym'],
        script: '', shots: ['Slide 1: bold title on brand colour', 'Slides 2–6: one mistake each with a photo', 'Last slide: free trial CTA'],
      },
      {
        pillar: 'trend', platform: 'instagram', format: 'reel', hour: 20,
        title: 'Trending audio: "Gym vs my excuses"',
        caption: 'Every excuse, every day 😅 Which one is yours? Tag a friend who needs this.',
        hashtags: ['#GymHumor', '#FitnessReels', '#PuneGym'],
        script: 'Use the trending "me vs me" audio. Left: excuse ("It\'s raining"). Right: member walking in anyway. 4 quick pairs.',
        shots: ['Rainy window', 'Member walking in with an umbrella', 'Alarm at 5:30 am', 'Member on the treadmill at 6 am'],
      },
      {
        pillar: 'behind_the_scenes', platform: 'instagram', format: 'story', hour: 7,
        title: '6 am at Pulse: meet the morning crew',
        caption: 'Good morning from the 6 am squad ☀️ Who is joining tomorrow?',
        hashtags: ['#MorningWorkout', '#PulseFitness'],
        script: '15-second walk-through of the floor at 6 am, wave from 3 members, poll sticker "Morning or evening?"',
        shots: ['Door opening at 5:55 am', 'Members warming up', 'Poll sticker'],
      },
      {
        pillar: 'offer', platform: 'google', format: 'post', hour: 11,
        title: 'Google post: free trial week',
        caption: 'Free trial week at Pulse Fitness, Baner. Try any batch (gym, yoga, zumba) for free this week. Call or WhatsApp to book.',
        hashtags: [], script: '', shots: ['Wide photo of the gym floor in daylight'],
      },
      {
        pillar: 'festival', platform: 'instagram', format: 'post', hour: 9,
        title: 'Dussehra: burn your excuses',
        caption: 'This Dussehra, let\'s burn the excuses, not the motivation 🔥 Happy Dussehra from team Pulse!',
        hashtags: ['#HappyDussehra', '#PuneGym', '#PulseFitness'],
        script: '', shots: ['Team photo with festive props'],
      },
    ],
    social: [
      { platform: 'instagram', handle: '@pulsefitness.baner', followers: 3840, status: 'connected' },
      { platform: 'facebook', handle: 'Pulse Fitness Studio', followers: 1210, status: 'connected' },
      { platform: 'google_business', handle: 'Pulse Fitness Studio, Baner', followers: null, status: 'connected' },
      { platform: 'whatsapp_business', handle: '+91 90000 11111', followers: null, status: 'connected' },
      { platform: 'youtube', handle: '', followers: null, status: 'disconnected' },
    ],
  },
  {
    business: {
      id: 2,
      name: 'Shine Auto Studio',
      category: 'car_detailing',
      category_label: 'Car detailing & accessories',
      city: 'Delhi',
      area: 'Karol Bagh',
      phone: '9000022222',
      brand_voice: 'Confident car-lover. Short sentences, a little Hinglish, always show the finish. No fake discounts.',
      target_audience: 'Car owners in West and Central Delhi, 25–45, with cars under 5 years old who care how they look.',
      google_review_link: 'https://g.page/r/shine-auto-karolbagh/review',
      opening_hours: '10 am – 8 pm, closed Tuesday',
    },
    services: [
      { key: 'ceramic_coating', name: 'Ceramic coating', price: [18000, 35000], weight: 22 },
      { key: 'ppf', name: 'Paint protection film', price: [65000, 140000], weight: 7 },
      { key: 'interior_cleaning', name: 'Interior deep clean', price: [2500, 4500], weight: 18 },
      { key: 'polishing', name: 'Rubbing & polishing', price: [2000, 3500], weight: 16 },
      { key: 'android_stereo', name: 'Android screen', price: [9500, 18000], weight: 20 },
      { key: 'dashcam', name: 'Dashcam', price: [4500, 9000], weight: 17 },
    ],
    sources: { instagram: 30, google: 18, whatsapp: 18, website: 10, justdial: 14, indiamart: 4, walkin: 6 },
    win: { instagram: 0.12, google: 0.4, whatsapp: 0.3, website: 0.28, justdial: 0.17, indiamart: 0.22, walkin: 0.5 },
    hours: [0, 0, 0, 0, 0, 0, 0, 1, 2, 4, 6, 8, 8, 6, 5, 5, 6, 7, 8, 9, 7, 4, 2, 1],
    cars: ['Creta', 'Swift', 'Brezza', 'Seltos', 'Nexon', 'XUV700', 'Thar', 'City', 'Baleno', 'Fortuner', 'Verna', 'Scorpio-N'],
    messages: {
      ceramic_coating: [
        '{car} ke liye ceramic coating ka rate kya hai? 9H wala chahiye',
        'Graphene coating vs ceramic, which is better for a black {car}?',
        'New {car} delivery next week, want coating before I drive it. Price?',
      ],
      ppf: ['PPF full body for my new {car}, how much and how many days?', 'Matte PPF hota hai kya? {car} ke liye quote bhejo'],
      interior_cleaning: ['Interior deep cleaning chahiye, dog hair everywhere. {car} hai', 'Seats pe coffee gir gayi, {car}. Cleaning ho jayegi aaj?'],
      polishing: ['Rubbing polishing karwani hai Diwali se pehle, {car} hai', 'Swirl marks on my {car}, can polishing fix it?'],
      android_stereo: ['Android screen with reverse camera for {car}, best price batao', '{car} me 10 inch android lagwana hai, wireless carplay wala'],
      dashcam: ['Dashcam front + rear install in {car}. Today possible?', '70mai dashcam lagate ho? {car} ke liye'],
    },
    urgent: ['Kal shaadi mein jaana hai, aaj hi polish ho sakti hai? {car}', 'Need it done today, how soon can you take my {car}?'],
    frustrated: [
      'Last time coating mein water spots aa gaye. Fix karoge ya nahi? {car}',
      'Called 3 times for a quote, nobody picked up. {car} ceramic coating price please.',
    ],
    followups: ['Ok, Saturday 11 baje la raha hoon', 'Last price kya hoga?', 'Location share karo', 'Booked, thank you!'],
    replies: [
      'Hi {name}! {service} for your car starts at ₹{price}. Takes 1–2 days. Want a slot this week?',
      'Hello {name}, thanks! {service} is ₹{price} all-inclusive. Free pickup in Karol Bagh area.',
    ],
    reviews: {
      good: [
        ['Got ceramic coating done on my Creta. The finish is mirror-like and they delivered on time.', ['Finish quality', 'On-time delivery']],
        ['Interior cleaning was unbelievable, my Swift smells new again. Fair price.', ['Interior cleaning', 'Fair price']],
        ['Android screen install was neat, no loose wires. Explained every feature.', ['Neat installs', 'Explains clearly']],
        ['PPF on my XUV700 is flawless. Worth every rupee.', ['Finish quality']],
        ['Honest people. They told me polishing was enough, did not upsell coating.', ['Honest advice', 'Fair price']],
        ['Free pickup and drop saved me a whole day. Great service.', ['Pickup & drop', 'On-time delivery']],
      ],
      ok: [['Good work on the coating but took one day more than promised.', ['Finish quality'], ['Delays']]],
      bad: [
        ['Was promised delivery by 5 pm, got the car at 9 pm. No call to update.', ['Delays', 'No updates']],
        ['Water spots appeared after 2 weeks of coating. Still waiting for the fix.', ['Coating quality', 'Slow replies']],
        ['Dashcam wire is hanging near the mirror. Sloppy finishing.', ['Sloppy installs']],
        ['Quoted ₹22,000 on call, billed ₹26,500. Not transparent.', ['Pricing']],
      ],
    },
    ideas: [
      {
        pillar: 'offer', platform: 'instagram', format: 'reel', hour: 19,
        title: 'Pre-Diwali ceramic coating offer',
        caption: 'Diwali pe gaadi bhi chamakni chahiye ✨ Ceramic coating from ₹18,000 with free interior clean, only till Sunday.\n\nDM "SHINE" to book your slot.',
        hashtags: ['#CeramicCoating', '#DelhiCars', '#KarolBagh', '#DiwaliOffer', '#CarDetailing'],
        script: 'Hook: water beading on the bonnet in slow motion.\nMiddle: 50/50 shot (half polished, half dull).\nOffer card: "₹18,000 + free interior clean".\nCTA: "DM SHINE. Only 6 slots left."',
        shots: ['Hose water beading on a black bonnet', '50/50 paint split under the shop light', 'Team member applying coating', 'Car rolling out at golden hour'],
      },
      {
        pillar: 'testimonial', platform: 'instagram', format: 'reel', hour: 19,
        title: 'Before/after: 5-year-old Creta looks new',
        caption: '5 years old. Looks 5 days old. 🚗✨ Full correction + ceramic coating on this Creta.\n\nWhat should we do next? Comment your car.',
        hashtags: ['#BeforeAndAfter', '#CarDetailing', '#Creta', '#DelhiCars'],
        script: 'Hook: owner\'s reaction at delivery.\nCut to: swirl marks under torch → polishing → final shine.\nEnd: owner thumbs up.',
        shots: ['Torch showing swirl marks', 'Machine polishing close-up', 'Owner seeing the car', 'Final 360° walk-around'],
      },
      {
        pillar: 'educational', platform: 'instagram', format: 'carousel', hour: 12,
        title: 'Ceramic vs graphene vs PPF in 30 seconds',
        caption: 'Confused between ceramic, graphene and PPF? Here is the simple answer 👇 Save this before you spend ₹20,000+.',
        hashtags: ['#CeramicCoating', '#PPF', '#CarCare', '#DelhiCars'],
        script: '', shots: ['Slide per option: what it is, how long it lasts, price range', 'Last slide: "Not sure? WhatsApp us a photo"'],
      },
      {
        pillar: 'trend', platform: 'instagram', format: 'reel', hour: 20,
        title: 'Satisfying foam wash (trending audio)',
        caption: 'Volume up 🔊 Most satisfying 15 seconds of your day.',
        hashtags: ['#SatisfyingVideos', '#CarWash', '#Detailing'],
        script: 'Snow-foam cannon covering the car, pressure rinse, slow-motion beading. Use trending audio.',
        shots: ['Foam cannon close-up', 'Rinse from roof to bumper', 'Slow-mo beading'],
      },
      {
        pillar: 'behind_the_scenes', platform: 'instagram', format: 'story', hour: 17,
        title: 'How we prep paint before coating',
        caption: '3 steps before any coating: wash, decontaminate, polish. No shortcuts.',
        hashtags: ['#Detailing'], script: '3 short clips with text stickers, quiz sticker "Which step takes longest?"',
        shots: ['Clay bar on paint', 'IPA wipe-down', 'Paint depth gauge'],
      },
      {
        pillar: 'offer', platform: 'google', format: 'post', hour: 11,
        title: 'Google post: free pickup in Karol Bagh',
        caption: 'Free pickup and drop for any detailing job in Karol Bagh, Rajinder Nagar and Patel Nagar this month. Call or WhatsApp to book.',
        hashtags: [], script: '', shots: ['Photo of the pickup van with the logo'],
      },
      {
        pillar: 'festival', platform: 'instagram', format: 'post', hour: 9,
        title: 'Dhanteras: new car? Protect it first',
        caption: 'Bought a new car this Dhanteras? 🪔 Congratulations! Protect the paint in its first week. Book a PPF or coating consult.',
        hashtags: ['#Dhanteras', '#NewCar', '#PPF', '#DelhiCars'], script: '', shots: ['New car with a marigold garland'],
      },
    ],
    social: [
      { platform: 'instagram', handle: '@shineautostudio.dl', followers: 6120, status: 'expired' },
      { platform: 'facebook', handle: 'Shine Auto Studio', followers: 2400, status: 'connected' },
      { platform: 'google_business', handle: 'Shine Auto Studio, Karol Bagh', followers: null, status: 'connected' },
      { platform: 'whatsapp_business', handle: '+91 90000 22222', followers: null, status: 'connected' },
      { platform: 'youtube', handle: '@shineautostudio', followers: 890, status: 'connected' },
    ],
  },
  {
    business: {
      id: 3,
      name: 'Smile Care Dental Clinic',
      category: 'dental_clinic',
      category_label: 'Dental clinic',
      city: 'Jaipur',
      area: 'Malviya Nagar',
      phone: '9000033333',
      brand_voice: 'Calm, caring and clear. Explain treatments simply, never scare people. English with a little Hindi.',
      target_audience: 'Families and young professionals in Malviya Nagar and Jagatpura; parents booking for children.',
      google_review_link: 'https://g.page/r/smilecare-jaipur/review',
      opening_hours: '10 am – 1:30 pm, 5 pm – 8:30 pm',
    },
    services: [
      { key: 'cleaning', name: 'Teeth cleaning', price: [1200, 1800], weight: 22 },
      { key: 'root_canal', name: 'Root canal', price: [6000, 9500], weight: 16 },
      { key: 'aligners', name: 'Braces & aligners', price: [45000, 120000], weight: 9 },
      { key: 'whitening', name: 'Teeth whitening', price: [8000, 15000], weight: 10 },
      { key: 'implant', name: 'Dental implant', price: [25000, 45000], weight: 8 },
      { key: 'checkup', name: 'Check-up', price: [500, 500], weight: 25 },
    ],
    sources: { google: 34, justdial: 18, whatsapp: 18, website: 12, instagram: 12, walkin: 6 },
    win: { google: 0.45, justdial: 0.22, whatsapp: 0.35, website: 0.33, instagram: 0.1, walkin: 0.6 },
    hours: [0, 0, 0, 0, 0, 0, 0, 1, 3, 6, 8, 8, 6, 3, 2, 3, 5, 7, 8, 7, 5, 3, 1, 0],
    messages: {
      cleaning: ['Teeth cleaning ka charge kitna hai? Saturday appointment mil jayega?', 'How much for scaling and polishing?'],
      root_canal: ['Do you accept insurance? Need a root canal', 'Root canal kitne sittings mein hota hai aur kharcha?'],
      aligners: ['Aligners vs braces cost for my 14 year old daughter?', 'Invisible aligners ka EMI option hai kya?'],
      whitening: ['Teeth whitening before my wedding in December, how many sittings?', 'Whitening is safe? Price please'],
      implant: ['Missing tooth, implant ka total kharcha kitna aayega?', 'Implant vs bridge, which is better for a 60 year old?'],
      checkup: ['Bleeding gums when brushing, should I come for a check-up?', 'Need a check-up for my 6 year old son, any slot this week?'],
    },
    urgent: ['Severe tooth pain since last night, need an appointment today please', 'Tooth broke while eating, very painful. Can the doctor see me this evening?'],
    frustrated: ['Called the clinic twice, line always busy. Is anyone there? Need appointment.', 'Booked online but nobody confirmed. Coming or not?'],
    followups: ['Ok, 5:30 pm works', 'Is parking available?', 'Can you send the location?', 'Thank you doctor, confirmed.'],
    replies: [
      'Hello {name}, {service} is ₹{price}. Dr. Mehta has a slot today at 6 pm. Shall I book it?',
      'Hi {name}! {service} costs ₹{price}. We are open 10–1:30 and 5–8:30. When suits you?',
    ],
    reviews: {
      good: [
        ['Dr. Mehta did my root canal painlessly. Explained everything clearly before starting.', ['Painless treatment', 'Explains clearly']],
        ['My son was scared but the doctor was so gentle. Very child-friendly clinic.', ['Good with kids', 'Gentle doctor']],
        ['Spotless clinic, every instrument is sterilised in front of you.', ['Hygiene']],
        ['Aligners are going great, regular follow-ups and WhatsApp reminders.', ['Follow-ups', 'Aligners']],
        ['Honest advice: told me I did not need a crown. Rare these days.', ['Honest advice']],
        ['Whitening results are great before my wedding. Thank you Smile Care!', ['Whitening results']],
      ],
      ok: [['Good doctor, but the waiting time was long even with an appointment.', ['Good doctor'], ['Waiting time']]],
      bad: [
        ['Waited 50 minutes despite an appointment. Reception was rude.', ['Waiting time', 'Reception']],
        ['Billing was more than the quote, extra X-ray charges not told before.', ['Pricing']],
        ['Filling fell out in 3 weeks. Had to pay again.', ['Treatment quality']],
      ],
    },
    ideas: [
      {
        pillar: 'educational', platform: 'instagram', format: 'reel', hour: 13,
        title: 'Is teeth cleaning painful? Dr. Mehta answers',
        caption: 'Is scaling painful? Does it make teeth weak? Dr. Mehta answers the 3 most common questions in 30 seconds 🦷',
        hashtags: ['#DentistJaipur', '#TeethCleaning', '#MalviyaNagar', '#SmileCare'],
        script: 'Hook: "Teeth cleaning se daant kamzor hote hain?"\nDoctor answers 3 myths, 8 seconds each.\nCTA: "Book a cleaning: link in bio."',
        shots: ['Doctor at the chair, facing camera', 'Close-up of the ultrasonic scaler (no patient)', 'Clinic reception'],
      },
      {
        pillar: 'testimonial', platform: 'instagram', format: 'reel', hour: 19,
        title: "Riya's aligner journey",
        caption: '8 months, zero metal 😁 Riya\'s invisible aligner journey, with her permission.\n\nFree aligner consultation this month.',
        hashtags: ['#Aligners', '#SmileMakeover', '#DentistJaipur'],
        script: 'Hook: smile reveal.\nRiya: "Nobody even noticed I was wearing them."\nTimeline photos month 1 → 8.\nCTA: free consultation.',
        shots: ['Smile reveal close-up', 'Riya talking to camera', 'Aligner case on the desk'],
      },
      {
        pillar: 'offer', platform: 'google', format: 'post', hour: 11,
        title: 'Google post: free check-up camp this Sunday',
        caption: 'Free dental check-up camp this Sunday, 10 am – 1 pm at Smile Care, Malviya Nagar. Kids welcome. Call or WhatsApp to reserve a slot.',
        hashtags: [], script: '', shots: ['Clinic front with the camp banner'],
      },
      {
        pillar: 'trend', platform: 'instagram', format: 'reel', hour: 20,
        title: 'Dentist reacts to viral brushing hacks',
        caption: 'Charcoal toothpaste? Lemon on teeth? 😬 Our dentist reacts to viral hacks.',
        hashtags: ['#DentistReacts', '#DentalTips', '#DentistJaipur'],
        script: 'Green-screen with 3 viral clips, doctor reacts with ✅ or ❌ and one line each.',
        shots: ['Doctor reacting, green screen'],
      },
      {
        pillar: 'behind_the_scenes', platform: 'instagram', format: 'story', hour: 10,
        title: 'How we sterilise every instrument',
        caption: 'Your safety, step by step: wash → autoclave → sealed pouch.',
        hashtags: ['#Hygiene'], script: 'Three clips with text stickers and a "Did you know?" quiz.',
        shots: ['Autoclave door', 'Sealed instrument pouch'],
      },
      {
        pillar: 'festival', platform: 'instagram', format: 'post', hour: 9,
        title: 'Diwali: sweets and your teeth',
        caption: 'Enjoy the mithai 🪔 Just rinse with water after sweets and brush before bed. Happy Diwali from Smile Care!',
        hashtags: ['#HappyDiwali', '#DentalTips', '#Jaipur'], script: '', shots: ['Mithai box with a toothbrush, flat lay'],
      },
    ],
    social: [
      { platform: 'instagram', handle: '@smilecare.jaipur', followers: 1980, status: 'connected' },
      { platform: 'facebook', handle: 'Smile Care Dental Clinic', followers: 3100, status: 'connected' },
      { platform: 'google_business', handle: 'Smile Care Dental Clinic', followers: null, status: 'connected' },
      { platform: 'whatsapp_business', handle: '+91 90000 33333', followers: null, status: 'connected' },
      { platform: 'youtube', handle: '', followers: null, status: 'disconnected' },
    ],
  },
]

export const FIRST_NAMES = [
  'Aarav', 'Priya', 'Rohan', 'Sneha', 'Vikram', 'Ananya', 'Karan', 'Pooja', 'Arjun', 'Neha', 'Rahul', 'Isha',
  'Siddharth', 'Kavya', 'Aditya', 'Meera', 'Nikhil', 'Riya', 'Manish', 'Shreya', 'Amit', 'Divya', 'Harsh',
  'Tanvi', 'Yash', 'Simran', 'Gaurav', 'Nisha', 'Varun', 'Aditi', 'Kunal', 'Sakshi', 'Deepak', 'Anjali',
]
export const LAST_NAMES = [
  'Sharma', 'Verma', 'Gupta', 'Mehta', 'Kapoor', 'Joshi', 'Singh', 'Patil', 'Kulkarni', 'Agarwal', 'Bansal',
  'Reddy', 'Iyer', 'Malhotra', 'Chopra', 'Deshmukh', 'Jain', 'Khanna', 'Saxena', 'Arora',
]

/* Titles for the posts each business published in past weeks, by type. */
export const PAST_TITLES = {
  gym: {
    offer: ['Monsoon offer: 2 months at ₹4,500', 'Couple membership: 20% off', 'Refer a friend, get 15 days free', 'Student plan at ₹1,999 a month'],
    testimonial: ["Member story: Arjun's first pull-up", "Neha's 8 kg in 3 months", 'Why Rahul switched to Pulse', "Sakshi's post-pregnancy fitness journey"],
    educational: ['Protein on an Indian diet', 'How many days a week should you train?', 'A 5-minute warm-up', 'Creatine: myth vs fact'],
    trend: ['POV: first day at the gym', 'Leg day walk (trending audio)', 'Gym playlist check'],
    behind_the_scenes: ['Deep-clean Sunday at Pulse', 'Meet coach Rahul', 'New dumbbells just arrived'],
    festival: ['Ganesh Chaturthi wishes', 'Independence Day: 15 push-up challenge', 'Navratri garba workout'],
  },
  car_detailing: {
    offer: ['Monsoon interior clean at ₹1,999', 'Dashcam with install at ₹4,999', 'Free wax with every polish', 'Android screen festive price'],
    testimonial: ['Before/after: Thar after a road trip', 'Fortuner PPF reveal', 'Customer story: Swift interior rescue', 'Seltos coating, 1 year later'],
    educational: ['How often to wash a coated car', 'Dashcam: front only or front + rear?', '3 signs your paint needs polishing'],
    trend: ['Satisfying interior extraction', 'Car transformation trend', 'ASMR: snow foam'],
    behind_the_scenes: ['A day at Shine Auto Studio', 'Meet our detailing team', 'Our new IR curing lamp'],
    festival: ['Ganesh Chaturthi wishes', 'Independence Day tricolour', 'Navratri: car pooja tips'],
  },
  dental_clinic: {
    offer: ['Monsoon offer: cleaning at ₹999', 'Free check-up for kids under 12', 'Whitening at ₹6,999 this month'],
    testimonial: ['Patient story: a painless root canal', "Aryan's braces come off!", 'Implant patient, 6 months later'],
    educational: ['How to brush properly (the 2-minute rule)', 'Bleeding gums: when to worry', 'Root canal myths busted', 'Kids and cavities: 5 tips'],
    trend: ['Dentist reacts: oil pulling', 'POV: you finally visit the dentist', 'Smile reveal trend'],
    behind_the_scenes: ['Inside our sterilisation room', 'Meet Dr. Mehta', 'Our new digital X-ray'],
    festival: ['Ganesh Chaturthi wishes', 'Raksha Bandhan: gift a smile', 'Navratri: fasting and oral care'],
  },
}

/* Upcoming festivals and days worth posting about. */
export const EVENTS = [
  ['2026-10-20', 'Dussehra', 'festival'],
  ['2026-10-29', 'Karwa Chauth', 'festival'],
  ['2026-11-06', 'Dhanteras', 'festival'],
  ['2026-11-08', 'Diwali', 'festival'],
  ['2026-11-14', "Children's Day", 'day'],
  ['2026-11-24', 'Guru Nanak Jayanti', 'festival'],
  ['2026-12-25', 'Christmas', 'festival'],
  ['2027-01-01', 'New Year', 'season'],
  ['2027-01-13', 'Lohri', 'festival'],
  ['2027-01-14', 'Makar Sankranti', 'festival'],
  ['2027-01-26', 'Republic Day', 'day'],
  ['2027-02-14', "Valentine's Day", 'day'],
  ['2027-03-08', "Women's Day", 'day'],
]

/* What each business could post for an event. */
export const EVENT_IDEAS = {
  gym: {
    Dussehra: 'Burn-your-excuses reel with a festive 2-week challenge',
    Diwali: '"Diwali sweets, no guilt" offer: 3 months + 1 free',
    'New Year': 'Resolution plan: 90-day transformation batch',
    "Women's Day": 'Free ladies-only strength workshop',
    default: 'Festive greeting reel with your members',
  },
  car_detailing: {
    Dhanteras: 'New car protection: PPF and coating consult',
    Diwali: 'Pre-Diwali shine package: polish + interior clean',
    'New Year': 'Fresh start detail for the new year',
    default: 'Festive greeting with a freshly detailed car',
  },
  dental_clinic: {
    Diwali: 'Sweets and your teeth: 3 quick tips',
    "Children's Day": 'Free kids check-up camp',
    "Valentine's Day": 'Smile makeover: whitening offer for couples',
    default: 'Festive greeting from the clinic team',
  },
}
