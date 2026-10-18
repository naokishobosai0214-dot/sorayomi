# そら読み（旧表記: 空読み・旧名: ならべて天気図）

地上天気図5枚まとめ。左の列に ASAS 48時間前・24時間前、真ん中に ASAS 最新(FSAS の初期値と同じ 00/12UTC)、右の列に FSAS24・FSAS48。

- ページ: https://narabete-tenkizu.pages.dev/ (Cloudflare Pages。GitHub Pages は 2026-10-14 に停止)
- 更新: 1日2回(9時・21時の図)。FSAS24・48 の初期値がそろったら GitHub Actions(`.github/workflows/update.yml`)が作り直して公開
- 出典: 気象庁ホームページ(地上天気図)を加工して作成。編集・加工の責任はならべて天気図にあります
- フォント: BIZ UDゴシック(SIL Open Font License、`fonts/OFL.txt`)
