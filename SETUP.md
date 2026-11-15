# Setup (for the project owner)

1. Supabase > Authentication > Sign In / Providers > Email: switch **Confirm email** OFF, Save.
2. Supabase > SQL Editor > New query: paste the whole content of each file in `supabase/migrations/`
   (in number order) and press **Run**. Running a file twice does no harm.
3. Never share the secret key (`sb_secret_...`). If it was shared, Settings > API Keys > delete it and create a new one.
