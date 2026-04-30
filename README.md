# Pro.-AM

鑷姩浠?PubMed 妫€绱?**CAR-M锛堝祵鍚堟姉鍘熷彈浣撳法鍣粏鑳烇級** 椤跺垔鏂囩尞锛屾彁鍙栨爣棰樹笌鎽樿锛屾瘡鏃ュ畾鏃剁炕璇戝苟鎺ㄩ€佽嚦閭銆?
## 鍔熻兘

- 馃攳 姣忔棩鑷姩妫€绱?PubMed 鏈€鏂版枃鐚?- 馃寪 鏍囬 + 鎽樿鑷姩缈昏瘧涓轰腑鏂?- 馃 AI 鏅鸿兘鎽樿锛圙LM-4-Flash锛屽熀浜庝綔鑰?鏈熷垔/鏍囬/鎽樿鐢熸垚涓枃瑙ｈ锛?- 馃搳 鑷姩鏌ヨ鏈熷垔 SCI/JCI/JCI5/涓闄㈠垎鍖猴紙EasyScholar锛?- 馃摟 閭欢鎺ㄩ€佽嚦 persist2021@163.com
- 馃攣 鑷姩鍘婚噸锛屼笉浼氶噸澶嶆帹閫?- 馃 GitHub Actions 瀹氭椂杩愯锛堝寳浜?07:30锛?- 馃搫 鏃犳憳瑕佹枃绔犺嚜鍔ㄨ烦杩?- 馃攢 Fallback 鏈哄埗锛氶《鍒婃煡璇㈡棤鏂版枃鐚椂鑷姩闄嶇骇鍒板箍娉涙绱?
## 妫€绱㈡ā鍧?
| 妯″潡 | 涓婚 | 鎺ㄩ€佹椂闂达紙鍖椾含锛?|
|------|------|-----------------|
| 1 | CAR-M锛堝祵鍚堟姉鍘熷彈浣撳法鍣粏鑳烇級 | 07:30 |

### 妫€绱㈠紡

**涓绘绱紙闄愬畾 77 鏈腑绉戦櫌 1 鍖洪《鍒婏級锛?*

``
("chimeric antigen receptor macrophage*"[Title/Abstract] OR 
 "CAR macrophage*"[Title/Abstract] OR 
 "CAR-M"[Title/Abstract] OR 
 "CAR-Mac"[Title/Abstract] OR 
 "chimeric antigen receptor"[Title] AND "macrophage*"[Title])
``

**Fallback 妫€绱紙涓嶉檺鏈熷垔锛岄《鍒婃棤鏂版枃鐚椂鑷姩瑙﹀彂锛夛細**

``
"chimeric antigen receptor macrophage*"[Title/Abstract] OR 
"CAR macrophage*"[Title/Abstract] OR 
"CAR-M"[Title/Abstract] OR 
"CAR-Mac"[Title/Abstract] OR 
("chimeric antigen receptor"[Title] AND "macrophage*"[Title])
``

鎵€鏈夋ā鍧楀潎闄愬畾 **77 鏈腑绉戦櫌 1 鍖烘湡鍒?*锛堣瑙?config_base.py锛夈€?
## 浣跨敤

1. Fork 鎴?Clone 鏈粨搴?2. 鍦ㄤ粨搴?Settings 鈫?Secrets and variables 鈫?Actions 鈫?New repository secret 涓坊鍔狅細
   - SMTP_AUTH_CODE 鈥?163 閭 SMTP 鎺堟潈鐮?   - ZHIPU_API_KEY 鈥?鏅鸿氨 AI API Key锛堢敤浜?AI 鏅鸿兘鎽樿锛屽彲閫夛級

## 椤圭洰缁撴瀯

``
Pro.-AM/
鈹溾攢鈹€ config_base.py          # 鍏变韩閰嶇疆锛堟湡鍒婄櫧鍚嶅崟銆侀偖绠憋級
鈹溾攢鈹€ config_car_m.py         # CAR-M 妫€绱㈣瘝 + fallback 妫€绱㈣瘝
鈹溾攢鈹€ pubmed_fetcher.py       # 鍏变韩鐖彇浠ｇ爜
鈹溾攢鈹€ README.md
鈹斺攢鈹€ .github/workflows/
    鈹斺攢鈹€ car_m.yml           # CAR-M 瀹氭椂浠诲姟
``

## 渚濊禆

``
pip install biopython deep-translator requests
``

## 鎵嬪姩杩愯

``
python pubmed_fetcher.py --config config_car_m
``