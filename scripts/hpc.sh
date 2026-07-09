#!/bin/bash
# 通过持久 tail -f | ssh 会话向 HPC 发送命令并等待输出。
# 前提：用户终端已运行  tail -n +1 -f hpc_cmds | ssh -T ... > hpc_out 2>&1
# 用法: bash hpc.sh '<远程命令>'   [超时秒数, 默认180]
SCR="/private/tmp/claude-501/-Users-qdxu-Downloads-PCM-database/2d301d17-80be-4d82-b885-ac0b194f5858/scratchpad"
CMDS="$SCR/hpc_cmds"
OUT="$SCR/hpc_out"
CMD="$1"
TIMEOUT="${2:-180}"

# 哨兵：远端执行后输出连续串 MARK；但写进命令文件时用 "A""B" 拼接，
# 使「回显的命令」不含连续串，只有「执行结果」才含 —— 避免误匹配回显。
RID="$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n')"
MARK="ZZDONE${RID}ZZ"        # 完整连续串（只出现在执行结果里）
START=$(wc -l < "$OUT")

# 追加命令 + 哨兵（拆分写法 + 退出码）
{
  printf '%s\n' "$CMD"
  printf 'echo "ZZDONE""%s""ZZ:""$?"\n' "$RID"
} >> "$CMDS"

elapsed=0
while ! grep -q "$MARK" "$OUT" 2>/dev/null; do
    sleep 0.3
    elapsed=$(python3 -c "print(round($elapsed+0.3,1))")
    if [ "$(python3 -c "print(1 if $elapsed>$TIMEOUT else 0)")" = "1" ]; then
        echo "[hpc.sh] 超时 ${TIMEOUT}s。已收到输出：" >&2
        tail -n +$((START+1)) "$OUT" | sed $'s/\r//g; s/\x1b\][0-9];[^\x07]*\x07//g; s/\x1b\[[0-9;?]*[a-zA-Z]//g'
        exit 124
    fi
done

# 清洗输出：去 CR、去标题转义、去 ANSI 颜色；剔除哨兵行
tail -n +$((START+1)) "$OUT" \
  | sed $'s/\r//g; s/\x1b\][0-9];[^\x07]*\x07//g; s/\x1b\[[0-9;?]*[a-zA-Z]//g' \
  | grep -v "$MARK"
echo "[exit:$(grep "$MARK" "$OUT" | tail -1 | sed 's/\r//g' | sed "s/.*${MARK}://")]"
