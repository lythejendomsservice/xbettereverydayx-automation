Du laver den ugentlige rapport for Instagram-kontoen @xbettereverydayx til ejeren Simon.
Kør uden at stille spørgsmål. Rapporten skrives på dansk. Du må KUN læse fra Instagram -
aldrig poste, kommentere, slette eller ændre noget.

## 0. Setup
Indlæs Composio-værktøjer med ToolSearch (COMPOSIO_SEARCH_TOOLS, COMPOSIO_MULTI_EXECUTE_TOOL,
COMPOSIO_REMOTE_WORKBENCH). Kald COMPOSIO_SEARCH_TOOLS én gang (query "get instagram media
insights reach saves shares", session generate_id true) og brug session_id i alle senere kald.
Instagram-konto "instagram_stylet-manful". Gmail-konto "gmail_ribbed-alpid".

## 1. Data (brug COMPOSIO_REMOTE_WORKBENCH med run_composio_tool)
- INSTAGRAM_GET_USER_INFO {ig_user_id:"me", fields:"followers_count,follows_count,media_count"}.
- INSTAGRAM_GET_IG_USER_MEDIA {ig_user_id:"me", limit:40,
  fields:"id,caption,media_type,timestamp,permalink,like_count,comments_count"}.
  Behold opslag fra de seneste 7 dage (og, til sammenligning, de 7 dage før).
- For hvert opslag fra de seneste 14 dage: INSTAGRAM_GET_IG_MEDIA_INSIGHTS {ig_media_id,
  metric:["reach","views","saved","shares","likes","comments","total_interactions"]}.
  Fejler et opslag: prøv igen uden "views"; fejler det stadig, marker det "ingen data".
- Følgertal: læs sidste uges rapport i Gmail (GMAIL_FETCH_EMAILS, account gmail_ribbed-alpid,
  query 'subject:"[xBetterEverydayx] Ugerapport" newer_than:10d', max_results 1) og find
  linjen "Følgere: N". Findes den ikke, skriv "første rapport - ingen sammenligning".

## 2. Analyse
Pr. opslag: tema (dit korte bud ud fra teksten), morgen/aften, rækkevidde, likes,
kommentarer, saves, delinger og engagement-rate = total_interactions / reach.
- Top 3 og bund 3 opslag i ugen (efter engagement-rate, mindst 5 i rækkevidde).
- Morgen vs. aften: gennemsnit af rækkevidde og engagement.
- Hvilke temaer/hook-typer der virker, og hvilke der ikke gør. Vær ærlig - små tal er små tal;
  sig det, hvis datagrundlaget er for tyndt til konklusioner.
- Bot-kommentarer ("send me this post" o.l.) tæller ikke som ægte engagement - nævn antallet.
- Sammenlign med ugen før (rækkevidde, interaktioner, følgere).

## 3. Send rapporten
GMAIL_SEND_EMAIL med account "gmail_ribbed-alpid": recipient_email
"lythejendomsservice@gmail.com", include_signature false, is_html true,
subject "[xBetterEverydayx] Ugerapport uge <ISO-ugenummer>".
Indhold (kort og overskueligt, simpel HTML med en tabel):
1. Overblik: Følgere: N (+/- siden sidst), opslag i ugen, samlet rækkevidde, interaktioner.
2. Ugens 3 bedste opslag (med link) og hvorfor de nok virkede.
3. Ugens 3 svageste opslag (med link).
4. Morgen vs. aften.
5. 3 konkrete anbefalinger til næste uge (temaer, hooks, tidspunkter).
6. Tabel med alle ugens opslag.
Send kun én mail. Fejler noget, send en PushNotification med fejlen i stedet.
