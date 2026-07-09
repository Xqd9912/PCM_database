#!/bin/bash
# 在 NSCC HPC 上扫描 xqd/xumeng/grc 三目录下所有含 INCAR 的计算目录。
# 用法: bash hpc_scan_nscc.sh <account_label>
# 输出 TSV 到 stdout，path 以 <account_label>/ 为前缀（跨账号唯一）。
ACCT="$1"
DIRS="xqd xumeng grc"
cd ~ || exit 1

printf 'path\tibrion\ttebeg\tteend\tnsw\tpotim\tcontcar_size\tspecies\tcounts\n'

for base in $DIRS; do
  [ -d "$base" ] || continue
  find "$base" -name INCAR -type f 2>/dev/null | while read -r inc; do
    d=$(dirname "$inc")
    vals=$(awk '
      function grab(line, key,   v){
        if (toupper(line) ~ key && line ~ /=/) {
          v=line; sub(/.*=/,"",v); gsub(/\r/,"",v);
          if (match(v,/-?[0-9]+\.?[0-9]*/)) return substr(v,RSTART,RLENGTH);
        }
        return "";
      }
      { s=$0; sub(/[!#].*/,"",s); n=split(s,a,";");
        for(i=1;i<=n;i++){
          t=grab(a[i],"IBRION"); if(t!="")ib=t;
          t=grab(a[i],"TEBEG");  if(t!="")tb=t;
          t=grab(a[i],"TEEND");  if(t!="")tn=t;
          t=grab(a[i],"NSW");    if(t!="")ns=t;
          t=grab(a[i],"POTIM");  if(t!="")po=t;
        }
      }
      END{printf "%s\t%s\t%s\t%s\t%s", ib,tb,tn,ns,po}' "$inc")
    if [ -s "$d/CONTCAR" ]; then csize=$(stat -c %s "$d/CONTCAR" 2>/dev/null); else csize=0; fi
    sf="$d/CONTCAR"; [ -s "$sf" ] || sf="$d/POSCAR"
    sp=""; ct=""
    if [ -s "$sf" ]; then
      sp=$(sed -n '6p' "$sf" 2>/dev/null | tr -s ' \t' ' ' | sed 's/^ //;s/ $//;s/\r//')
      ct=$(sed -n '7p' "$sf" 2>/dev/null | tr -s ' \t' ' ' | sed 's/^ //;s/ $//;s/\r//')
    fi
    printf '%s/%s\t%s\t%s\t%s\t%s\n' "$ACCT" "$d" "$vals" "$csize" "$sp" "$ct"
  done
done
