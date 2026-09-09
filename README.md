# KEIBA NOTE V5.1

V4の収支管理機能を維持しながら、Supabase Freeを使ったPC・iPhoneクラウド同期、ログイン、V4データ移行、JSONバックアップ/復元を追加した版です。

## セットアップ
1. SupabaseでFreeプロジェクトを作成。
2. SQL Editorで `supabase.sql` を全量実行。
3. Settings > API Keys から Project URL と Publishable key を確認。
4. `config.js` の `YOUR_SUPABASE_URL` と `YOUR_SUPABASE_PUBLISHABLE_KEY` を置き換える。
5. `index.html` / `app.js` / `style.css` / `config.js` をGitHub Pagesへアップロード。
6. PCで新規登録またはログイン。
7. 初回ログイン時にV4のlocalStorageデータがあれば、クラウドへ移行する確認が出ます。
8. iPhoneでも同じメールアドレスとパスワードでログインします。

## セキュリティ
ブラウザにはSupabase Publishable keyだけを設定してください。`secret` / `service_role` keyは絶対に `config.js` に入れないでください。テーブルはRLSでユーザー自身の行だけを読書きできるようにしています。

## 注意
Supabase Freeは低活動が7日間続くプロジェクトを自動停止することがあります。停止した場合はSupabase DashboardからResumeできます。Freeでは自動バックアップが含まれないため、アプリの「バックアップ保存」も利用してください。
