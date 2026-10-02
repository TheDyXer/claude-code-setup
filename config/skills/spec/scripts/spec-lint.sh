#!/bin/bash
# spec-lint.sh — /spec skill の決定論チェッカ。検査内容の正本はこの --help。
# 出力: [OK|WARN|FAIL] C<n>: 理由   / exit 0 = FAIL ゼロ, 1 = FAIL あり
# 依存ゼロ (bash + BSD/GNU grep/awk/sed/date)。日本語リテラルは UTF-8 バイト列 grep。
set -u

usage() {
cat <<'HELP'
spec-lint.sh — /spec スペックファイルの決定論チェッカ (正本)

使い方:
  spec-lint.sh <spec.md>          単発 (手順6 step5: done 遷移の最終検査)
  spec-lint.sh --draft <spec.md>  起草時 (C11 有効・done 系検査は非対象)
  spec-lint.sh --all [dir ...]    fleet sweep (手順0 入口・一括後始末。省略時 ./specs と ~/specs)
  spec-lint.sh --self             skill 自己検査 (SKILL.md サイズ・同梱物)
  spec-lint.sh --hook             PostToolUse hook 用 (stdin JSON→対象なら単発実行。常に exit 0)
  spec-lint.sh --session-start    SessionStart hook 用 (cwd の未消化 spec 通知。常に exit 0)

チェック一覧 (retro-fit 実証: 19本の実 spec で誤検知0を確認した検査系のみ搭載):
  C1  ヘッダ整合: status 行 BNF (draft|approved|implementing|done|done-partial (pending: AC-n[,AC-m] trigger=<非空>)|killed)
      / done⇒completed 日付充足 / done-partial⇒completed=宣言日 / §13最大日付 ≤ max(completed, log 最新日付)
      / status≥approved で log 最新 r エントリに gateA:残0（r1 だけでは不可）/ done-partial の trigger 非空
      / lint 行 (単発=案内, --all=done∧未→FAIL)。log は単一行に ` / ` 区切りで追記する記法
  C2  AC 判定の存在検査: マーク付き AC([x][!][~][-]) ⇒ 証拠台帳に行+アンカー非空 / [~] 行に (BLOCKED: 理由 trigger=非空) / [-] 行に N/A:
      / done∧([ ]|[!]|[~]) 残→FAIL / done-partial∧([!]|[ ]) 残→FAIL / done-partial の [~] 集合 = status 行 pending リスト
  C3  ID 差集合: §13 出現 D/T/F-n ⇔ §12 定義。日付断片(D-2026等)は除外。§12 抽出が空なら「見出し欠落疑い」を別フラグで出す
  C5' 証拠緩和検査: 台帳アンカーのパス実在 (specs/evidence/) / コマンド AC を持つ spec の §13 に行頭 `exit N` ≥1
      (AC 行内の (exit 0) 書式リテラルでは満たさない — 実行フェンスの生出力のみが証拠)
      (旧 C5 逐語全数検査は retro-fit 0/15 ロックアウトで棄却→C5' に緩和。再導入禁止)
  C6  テンプレ見出し ## 1.〜## 13. の欠落検出 (空セクション≠見出し欠落を区別)
  C7  揮発 ID 参照 (workflow wf_… 等) の検出 — 証拠参照はコミットハッシュ/ファイルパスのみ
  C11 --draft: TBD/検討の余地/未定 の残存 (「未確認（ゲートB前に質問予定）」は draft のみ許容) + AC 赤旗
      ①存在確認/--help/import 単体 ②OR 束ね (heuristic→WARN)。非 draft では「未確認（ゲートB前…」残存→FAIL
  C12 完了報告完全性: done|done-partial ⇒ 固定7キー存在 ∧ 「(未」残存ゼロ (lint出力キーのみ単発=案内・--all=FAIL — 実行→貼付の順の卵鶏回避)
  C8  supersedes/superseded-by の対称性 (--all)
  C9  slug 重複 = 正本分裂の疑い (--all)。moved-to: スタブは除外 (スタブ自体の検査も C0 で打ち切り)
  C10 done-partial pending 一覧 (--all)
  C13 stale implementing: §13 最終日付が7日超過去 (--all)
  C14 --self: SKILL.md ≤ 36,864B / scripts 同梱物の存在

棄却済み (再導入禁止):
  C4 曖昧語 grep — retro-fit で固有名詞(ChromeFast等)への誤検知ほぼ100%。曖昧語検出はゲートA subagent の意味判定が担当。
  C5 逐語フェンス全数検査 — retro-fit で既存運用 0/15 全滅ロックアウト。C5' に緩和済み。
重量予算の記録: SKILL.md 初期目標 34KiB → 36KiB に再裁定 (2026-07-08, 不変条文 carry-over の保全を優先)。
敵対検証の記録 (2026-07-08, 10 finder / 23 findings): C1(d) 最新r検査化・C5' §13行頭化・C12 7キー+lint出力
  単発除外・trigger/理由 非空化 — lint を実際に騙せた検査穴4件を封鎖済み。
  C14 の WARN は「機構追加の兆候」— 足す前に削るものを探せ。

旧形式 (log: 行なし) は [legacy] タグ付きで FAIL→WARN に自動降格 (first-touch 正規化が改訂節の手順)。
正規化済み旧 spec (log に migrated ありかつ gateA:残0 なし = v2 パイプライン未通過) も同様に降格 —
  gateA 履歴の捏造を要求しないため。v2 改訂で gateA を初獲得した時点から厳格モード。
HELP
}

FAILS=0; WARNS=0; LEGACY=0
emit() { # emit LEVEL ID MSG  (legacy なら FAIL→WARN 降格)
  local lv="$1" id="$2" msg="$3"
  if [ "$lv" = FAIL ] && [ "$LEGACY" = 1 ]; then lv=WARN; msg="[legacy] $msg"; fi
  case "$lv" in FAIL) FAILS=$((FAILS+1));; WARN) WARNS=$((WARNS+1));; esac
  echo "[$lv] $id: $msg"
}

sec() { # sec N FILE — "## N." から次の "## " までを出力
  awk -v n="$1" 'BEGIN{f=0} $0 ~ "^## "n"\\." {f=1; next} f && /^## / {exit} f' "$2"
}
subsec() { # subsec HEADING FILE — "### HEADING" から次の ### / ## までを出力
  awk -v h="$1" 'BEGIN{f=0} f && (/^### /||/^## /) {exit} f {print} index($0,"### "h)==1 {f=1}' "$2"
}
maxdate() { grep -oE '20[0-9]{2}-[01][0-9]-[0-3][0-9]' | sort | tail -1; }

lint_file() { # lint_file FILE MODE(single|draft|all)
  local f="$1" mode="$2"
  [ -f "$f" ] || { emit FAIL C0 "$f が存在しない"; return; }
  if grep -q '^moved-to:' "$f"; then
    echo "── $f"; echo "[OK] C0: moved-to スタブ → $(grep -m1 '^moved-to:' "$f" | sed 's/^moved-to:[[:space:]]*//')"
    return
  fi
  echo "── $f"
  LEGACY=0; grep -q '^- log:' "$f" || LEGACY=1
  [ "$LEGACY" = 1 ] && echo "     (legacy 形式: log: 行なし — FAIL は WARN に降格)"
  if [ "$LEGACY" = 0 ] && grep -m1 '^- log:' "$f" | grep -q 'migrated (' && ! grep '^- log:' "$f" | grep -q 'gateA:残0'; then
    LEGACY=1; echo "     (正規化済み旧 spec: gateA 未獲得 — FAIL は WARN に降格。v2 改訂で厳格化)"
  fi

  # ---- header parse ----
  local status completed logline logmax lintv
  status=$(grep -m1 '^- status:' "$f" | sed 's/<!--.*//' | sed 's/^- status:[[:space:]]*//; s/[[:space:]]*$//')
  completed=$(grep -m1 '^- created:' "$f" | sed 's/<!--.*//' | grep -oE 'completed: [^ ]+' | head -1 | sed 's/completed: //')
  logline=$(grep '^- log:' "$f" | tr '\n' ' ' || true)
  logmax=$(printf '%s' "$logline" | maxdate || true)
  lintv=$(grep -m1 '^- lint:' "$f" | sed 's/<!--.*//' | sed 's/^- lint:[[:space:]]*//; s/[[:space:]]*$//')
  local base="" pend="" trig="" rtail=""
  case "$status" in
    draft|approved|implementing|done|killed) base="$status" ;;
    done-partial\ \(pending:*trigger=*\))
      base="done-partial"
      pend=$(printf '%s' "$status" | sed 's/.*pending:[[:space:]]*//; s/[[:space:]]*trigger=.*//' | tr -d ' ')
      [ -n "$pend" ] || emit FAIL C1 "done-partial の pending リストが空"
      trig=$(printf '%s' "$status" | sed 's/.*trigger=//; s/)$//' | tr -d ' ')
      [ -n "$trig" ] || emit FAIL C1 "done-partial の trigger が空（再検証条件を書く）"
      ;;
    "") emit FAIL C1 "status 行が見つからない" ;;
    *)  emit FAIL C1 "status が enum 外: '$status'（killed の理由は log 行へ。括弧注記可は done-partial のみ）" ;;
  esac

  # C1(b) 日付充足
  if [ "$base" = done ]; then
    case "${completed:-未}" in 20[0-9][0-9]-*) : ;; *) emit FAIL C1 "status: done なのに completed が日付でない ('${completed:-無}')" ;; esac
  fi
  if [ "$base" = done-partial ]; then
    case "${completed:-未}" in 20[0-9][0-9]-*) : ;; *) emit FAIL C1 "done-partial は completed=宣言日 必須 ('${completed:-無}')" ;; esac
  fi
  if [ "$base" = killed ] && [ -n "$logline" ]; then
    printf '%s' "$logline" | grep -qE '20[0-9]{2}-[01][0-9]-[0-3][0-9]' || emit FAIL C1 "killed の終端日付が log 行にない"
  fi
  # C1(c) §13 最大日付 ≤ max(completed, log最新)
  if [ "$base" = done ] || [ "$base" = done-partial ] || [ "$base" = killed ]; then
    local s13max ref
    s13max=$(sec 13 "$f" | maxdate || true)
    ref=$(printf '%s\n%s\n' "${completed:-}" "${logmax:-}" | grep -E '^20' | sort | tail -1 || true)
    if [ -n "${s13max:-}" ] && [ -n "${ref:-}" ] && [ "$s13max" \> "$ref" ]; then
      emit FAIL C1 "§13 の最大日付 $s13max が completed/log ($ref) より新しい — done 後の無断追記"
    fi
  fi
  # C1(d) gateA トークン — 最新 r エントリ基準 (r1 の遺物では通らない)
  case "$base" in approved|implementing|done|done-partial)
    rtail=$(printf '%s' "$logline" | sed -n 's/.*\(r[0-9][0-9]* (.*\)$/\1/p')
    printf '%s' "${rtail:-$logline}" | grep -q 'gateA:残0' || emit FAIL C1 "status≥approved なのに log 最新 r エントリに gateA:残0 トークンがない" ;;
  esac
  # C1(e) lint 行
  if [ "$mode" = all ]; then
    if [ "$base" = done ] || [ "$base" = done-partial ]; then
      case "$lintv" in PASS*) : ;; *) emit FAIL C1 "done なのに lint 行が PASS でない ('${lintv:-無}')" ;; esac
    fi
  elif [ "$mode" = single ]; then
    case "$lintv" in 未) echo "[OK] C1: lint 行は PASS 後に更新し、この出力を完了報告に貼ること" ;; esac
  fi

  # ---- C6 見出し ----
  local i missing=""
  for i in 1 2 3 4 5 6 7 8 9 10 11 12 13; do
    grep -qE "^## $i\." "$f" || missing="$missing $i"
  done
  [ -n "$missing" ] && emit FAIL C6 "テンプレ見出しが欠落: §${missing}（空セクションではなく見出し自体が無い）"

  # ---- C2 AC 判定 ----
  local s11 ledger acline n mark
  s11=$(sec 11 "$f")
  ledger=$(subsec "証拠台帳" "$f")
  if [ -n "$s11" ]; then
    if [ "$base" = done ]; then
      printf '%s\n' "$s11" | grep -qE '^\- \[( |!|~)\] AC-' && emit FAIL C2 "done なのに [ ]/[!]/[~] の AC が残存（done は全て [x] か [-]）"
    fi
    if [ "$base" = done-partial ]; then
      printf '%s\n' "$s11" | grep -qE '^\- \[(!| )\] AC-' && emit FAIL C2 "done-partial なのに [!] か [ ] の AC が残存（pending 可は [~] のみ）"
      local tset pset
      tset=$(printf '%s\n' "$s11" | grep -E '^\- \[~\] AC-[0-9]+' | sed -E 's/^- \[~\] (AC-[0-9]+[a-z]?).*/\1/' | sort | tr '\n' ',' | sed 's/,$//')
      pset=$(printf '%s' "$pend" | tr ',' '\n' | sort | tr '\n' ',' | sed 's/,$//')
      [ "$tset" = "$pset" ] || emit FAIL C2 "status 行 pending ($pset) と §11 の [~] 集合 ($tset) が不一致"
    fi
    while IFS= read -r acline; do
      [ -n "$acline" ] || continue
      n=$(printf '%s' "$acline" | grep -oE 'AC-[0-9]+[a-z]?' | head -1)
      mark=$(printf '%s' "$acline" | sed -E 's/^- \[(.)\].*/\1/')
      [ -n "$n" ] || continue
      if [ "$mark" != " " ]; then
        if [ -n "$ledger" ]; then
          printf '%s\n' "$ledger" | awk -F'|' -v ac="$n" 'BEGIN{found=0} $2 ~ (ac"([^0-9]|$)") {found=1; if ($3 ~ /[^ \t]/) ok=1} END{print (found&&ok)?1:0}' | grep -q 1 \
            || emit FAIL C2 "$n はマーク済みだが証拠台帳に行が無い/アンカーが空"
        else
          emit FAIL C2 "マーク付き AC ($n) があるのに証拠台帳セクションが無い"
        fi
      fi
      [ "$mark" = "~" ] && { printf '%s' "$acline" | grep -qE '\(BLOCKED: [^)]+ trigger=[^) ]' || emit FAIL C2 "$n [~] に (BLOCKED: 理由 trigger=条件) がない（理由と trigger は両方非空）"; }
      [ "$mark" = "-" ] && { printf '%s' "$acline" | grep -q 'N/A:' || emit FAIL C2 "$n [-] に (N/A: 正当化) がない"; }
    done < <(printf '%s\n' "$s11" | grep -E '^\- \[[x!~ -]\] AC-[0-9]+' || true)
  fi

  # ---- C3 ID 差集合 ----
  local s12 s13 refs defs undef
  s12=$(sec 12 "$f"); s13=$(sec 13 "$f")
  if [ -n "$s13" ]; then
    if [ -z "$s12" ]; then
      emit FAIL C3 "§12 セクションが抽出できない — 見出し欠落の疑い（C6 連動）。ID 未定義とは別問題"
    else
      refs=$(printf '%s\n' "$s13" | grep -oE '(^|[^A-Za-z])[DTF]-[0-9]{1,3}([^0-9]|$)' | grep -oE '[DTF]-[0-9]{1,3}' | sort -u || true)
      defs=$(printf '%s\n' "$s12" | grep -oE '^\- [DTF]-[0-9]{1,3}' | grep -oE '[DTF]-[0-9]+' | sort -u || true)
      undef=$(comm -23 <(printf '%s\n' "$refs" | grep . || true) <(printf '%s\n' "$defs" | grep . || true) | tr '\n' ' ' || true)
      [ -n "${undef// /}" ] && emit FAIL C3 "§13 が参照するが §12 に定義が無い ID: ${undef}（ペアリング違反）"
    fi
  fi

  # ---- C5' 証拠緩和 ----
  local pth root
  if [ -n "$ledger" ]; then
    root=$(cd "$(dirname "$f")/.." 2>/dev/null && pwd)
    while IFS= read -r pth; do
      [ -n "$pth" ] || continue
      [ -f "$root/$pth" ] || [ -f "$(dirname "$f")/$pth" ] || emit WARN C5 "台帳参照パスが実在しない: $pth"
    done < <(printf '%s\n' "$ledger" | grep -oE 'specs/evidence/[^ |)`]+' | sort -u || true)
  fi
  if printf '%s\n' "$s11" | grep -qE '^\- \[[x!~-]\] AC-[0-9]+.*\`[^`]+\`'; then
    if [ "$base" = done ] || [ "$base" = done-partial ]; then
      printf '%s\n' "$s13" | grep -qE '^exit [0-9]+' || emit FAIL C5 "コマンド AC があるのに §13 に行頭 exit N の生出力が1つも無い（AC 行の (exit 0) 書式は証拠でない）"
    fi
  fi

  # ---- C7 揮発 ID ----
  local wfhits
  wfhits=$(grep -cE 'wf_[a-z0-9-]{6,}' "$f" 2>/dev/null | tr -d ' ')
  if [ "${wfhits:-0}" -gt 0 ] 2>/dev/null; then
    if [ "$base" = done ] || [ "$base" = done-partial ]; then
      emit FAIL C7 "揮発 ID 参照 (wf_…) が $wfhits 箇所 — コミットハッシュ/ファイルパスに置換"
    else
      emit WARN C7 "揮発 ID 参照 (wf_…) が $wfhits 箇所"
    fi
  fi

  # ---- C11 (draft) / 未確認 残存 (非 draft) ----
  if [ "$mode" = draft ]; then
    grep -nE 'TBD|検討の余地' "$f" | head -1 | grep -q . && emit WARN C11 "未確定語 (TBD/検討の余地) の残存: $(grep -nE 'TBD|検討の余地' "$f" | head -1 | cut -c1-80)"
    grep -nE '未定[^義]|未定$' "$f" | grep -v 'ゲートB前に質問予定' | head -1 | grep -q . && emit WARN C11 "「未定」の残存（該当なし+理由1行 か T 仮置きに）"
    local rf
    rf=$(printf '%s\n' "$s11" | grep -E '^\- \[ \]' | grep -cE '(test -f|ls -|--help|^\- \[ \] AC-[0-9]+: \`import )' | tr -d ' ')
    [ "${rf:-0}" -gt 0 ] 2>/dev/null && emit WARN C11 "AC 赤旗①: 存在確認/--help/import 単体の疑いが $rf 件（スタブでも通る AC は不合格）"
    rf=$(printf '%s\n' "$s11" | grep -E '^\- \[ \]' | grep -cE '\|\||または' | tr -d ' ')
    [ "${rf:-0}" -gt 0 ] 2>/dev/null && emit WARN C11 "AC 赤旗②: OR 束ねの疑いが $rf 件（1 AC 1 検証に分割）"
  else
    case "$base" in approved|implementing|done|done-partial)
      grep -q 'ゲートB前に質問予定' "$f" && emit FAIL C11 "「未確認（ゲートB前に質問予定）」が承認後も残存（R3 必須質問の未消化）" ;;
    esac
  fi

  # ---- C12 完了報告 ----
  if [ "$base" = done ] || [ "$base" = done-partial ]; then
    local rep k
    rep=$(subsec "完了報告" "$f")
    if [ -z "$rep" ]; then
      emit FAIL C12 "完了報告セクションが無い"
    else
      for k in "lint出力:" "AC結果:" "較正:" "監査:" "変更ファイル:" "T・F再掲:" "§12同期:"; do
        printf '%s\n' "$rep" | grep -q -- "- $k" || emit FAIL C12 "完了報告キー欠落: $k"
      done
      printf '%s\n' "$rep" | grep -v '^- lint出力:' | grep -q '(未' && emit FAIL C12 "完了報告に「(未」プレースホルダが残存"
      if printf '%s\n' "$rep" | grep '^- lint出力:' | grep -q '(未'; then
        if [ "$mode" = all ]; then
          emit FAIL C12 "lint出力キーが未貼付のまま done（--all は貼付済みを要求）"
        else
          echo "[OK] C12: lint出力キーにはこの実行の PASS 出力を貼って更新すること"
        fi
      fi
    fi
  fi
  LEGACY=0
}

fleet() { # fleet DIR...
  local dirs=() d f slugs
  if [ $# -gt 0 ]; then dirs=("$@"); else dirs=(./specs "$HOME/specs"); fi
  local files=()
  for d in "${dirs[@]}"; do
    [ -d "$d" ] || continue
    while IFS= read -r f; do files+=("$f"); done < <(find "$d" -maxdepth 1 -name '*.md' -type f 2>/dev/null | sort)
  done
  [ ${#files[@]} -eq 0 ] && { echo "[OK] C0: 対象 spec なし"; return; }
  for f in "${files[@]}"; do lint_file "$f" all; done
  # C8 supersede 対称性
  local sb ss
  for f in "${files[@]}"; do
    sb=$(grep -m1 -oE 'superseded-by: [^ )]+' "$f" 2>/dev/null | sed 's/superseded-by: //' || true)
    ss=$(grep -m1 -oE 'supersedes: [^ )]+' "$f" 2>/dev/null | sed 's/supersedes: //' || true)
    if [ -n "${sb:-}" ] && [ -f "$sb" ]; then grep -q "supersedes:.*$(basename "$f")" "$sb" || emit WARN C8 "$(basename "$f") → $sb に逆参照 (supersedes:) が無い"; fi
    if [ -n "${ss:-}" ] && [ -f "$ss" ]; then grep -q "superseded-by:.*$(basename "$f")" "$ss" || emit WARN C8 "$(basename "$f") が supersedes する $ss に superseded-by: が無い"; fi
  done
  # C9 slug 重複 (moved-to スタブは正本分裂でないため除外)
  slugs=$(for f in "${files[@]}"; do grep -q '^moved-to:' "$f" || basename "$f"; done | sort | uniq -d)
  [ -n "$slugs" ] && emit WARN C9 "slug 重複（正本分裂の疑い）: $(echo $slugs | tr '\n' ' ')"
  # C10 pending 一覧
  for f in "${files[@]}"; do
    grep -m1 -q '^- status: done-partial' "$f" 2>/dev/null && echo "[OK] C10: pending → $f : $(grep -m1 '^- status:' "$f" | sed 's/^- status:[[:space:]]*//' | cut -c1-80)"
  done
  # C13 stale implementing
  local weekago m
  weekago=$(date -v-7d +%F 2>/dev/null || date -d '7 days ago' +%F 2>/dev/null)
  for f in "${files[@]}"; do
    grep -m1 -qE '^- status:[[:space:]]*implementing' "$f" || continue
    m=$(sec 13 "$f" | maxdate || true)
    if [ -n "${m:-}" ] && [ -n "${weekago:-}" ] && [ "$m" \< "$weekago" ]; then
      emit WARN C13 "stale implementing: $f の §13 最終日付 ${m}（7日超）— 再開点確認を"
    fi
  done
}

self_check() {
  local d sz
  d=$(cd "$(dirname "$0")/.." && pwd)
  sz=$(wc -c < "$d/SKILL.md" 2>/dev/null | tr -d ' ')
  if [ -n "${sz:-}" ]; then
    if [ "$sz" -le 36864 ]; then echo "[OK] C14: SKILL.md ${sz}B ≤ 36864B"; else emit WARN C14 "SKILL.md ${sz}B > 36KiB — 機構追加の兆候。足す前に削れ"; fi
  else
    emit FAIL C14 "SKILL.md が見つからない ($d)"
  fi
  [ -f "$d/scripts/spec-lint.sh" ] && echo "[OK] C14: spec-lint.sh 同梱" || emit FAIL C14 "spec-lint.sh 不在"
  [ -f "$d/scripts/hooks-snippet.json" ] && echo "[OK] C14: hooks-snippet.json 同梱" || emit FAIL C14 "hooks-snippet.json 不在"
}

case "${1:-}" in
  --help|-h|"") usage; exit 0 ;;
  --draft) shift; lint_file "${1:?spec path}" draft ;;
  --all) shift; fleet "$@" ;;
  --self) self_check ;;
  --hook)
    p=$(python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); print((d.get("tool_input") or {}).get("file_path",""))
except Exception:
    pass' 2>/dev/null)
    case "${p:-}" in
      */specs/*.md) echo "spec-lint (hook, 非ブロッキング):"; lint_file "$p" single || true ;;
    esac
    exit 0 ;;
  --session-start)
    for f in ./specs/*.md; do
      [ -f "$f" ] || continue
      st=$(grep -m1 '^- status:' "$f" | sed 's/<!--.*//; s/^- status:[[:space:]]*//; s/[[:space:]]*$//')
      case "$st" in approved|implementing|done-partial*) echo "[spec] 未消化: $f ($st)";; esac
    done
    exit 0 ;;
  *) lint_file "$1" single ;;
esac

echo "── 結果: FAIL=$FAILS WARN=$WARNS"
[ "$FAILS" -eq 0 ] && exit 0 || exit 1