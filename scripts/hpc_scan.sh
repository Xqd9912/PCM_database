#!/bin/bash
# 在 HPC 上运行：扫描指定成员目录下所有含 INCAR 的计算目录，
# 提取分类所需字段，输出 TSV 到 stdout。
# 字段: path \t ibrion \t tebeg \t teend \t nsw \t potim \t contcar_size \t species \t counts
MEMBERS="xqd ysj yyf tsq sxf wh wyh hhy"
cd ~ || exit 1

printf 'path\tibrion\ttebeg\tteend\tnsw\tpotim\tcontcar_size\tspecies\tcounts\n'

for m in $MEMBERS; do
  [ -d "$m" ] || continue
  find "$m" -name INCAR -type f 2>/dev/null | while read -r inc; do
    d=$(dirname "$inc")
    # 一次 awk 读 INCAR 提取 5 个参数（去注释, 大小写不敏感, 取 = 后首个数值）
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
    # CONTCAR 大小
    if [ -s "$d/CONTCAR" ]; then csize=$(stat -c %s "$d/CONTCAR" 2>/dev/null); else csize=0; fi
    # 物种与计数（优先 CONTCAR，其次 POSCAR 的第6、7行）
    sf="$d/CONTCAR"; [ -s "$sf" ] || sf="$d/POSCAR"
    sp=""; ct=""
    if [ -s "$sf" ]; then
      sp=$(sed -n '6p' "$sf" 2>/dev/null | tr -s ' \t' ' ' | sed 's/^ //;s/ $//;s/\r//')
      ct=$(sed -n '7p' "$sf" 2>/dev/null | tr -s ' \t' ' ' | sed 's/^ //;s/ $//;s/\r//')
    fi
    printf '%s\t%s\t%s\t%s\t%s\n' "$d" "$vals" "$csize" "$sp" "$ct"
  done
done
