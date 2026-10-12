# Real-case test of the at-filing risk model

Sample: `data/validation/tanzlii_search_sample.csv`. model trained on 12,000 synthetic cases (2025 calibration).

* **56 decided cases** with a certain outcome (20 overran their disposition target, 36 finished within it); **10 left out** because their filing year alone cannot tell which side of the target they fall.
* Courts: High Court 40, Court of Appeal 16.

| Predictor | AUC (95% range) | Brier | Overruns rated High | On-time cases rated High |
|---|---|---|---|---|
| JusticeFlow model | 0.65 (0.48-0.81) | 0.239 | 0 of 20 | 0 of 36 |
| Baseline: court level only | 0.71 (0.58-0.83) | 0.221 | 11 of 20 | 5 of 36 |
| Baseline: court level + case type | 0.67 (0.50-0.83) | 0.216 | 8 of 20 | 2 of 36 |
| Model, everyone assumed unrepresented | 0.66 (0.48-0.82) | 0.233 | 0 of 20 | 0 of 36 |

**Within each court level** (does the model tell slow cases from fast ones at the same court?):

| Court | Cases | Overran | Mean risk, overran | Mean risk, on time | AUC within level |
|---|---|---|---|---|---|
| Court of Appeal | 16 | 11 | 49% | 53% | 0.36 |
| High Court | 40 | 9 | 0% | 1% | 0.38 |

**Every case:**

| Case | Court | Type | Outcome | Model risk |
|---|---|---|---|---|
| [Joseph F. Mbwiliza v Kobwa Mohamed Lyeeselo Msukuma & Others (Civil Appeal No. 227 of 2019) [2022] TZCA 699](https://tanzlii.org/akn/tz/judgment/tzca/2022/699) | Court of Appeal | Civil | overran | 62% |
| [Peter Olotai v Rebeca Toan Laizer & Others (Civil Appeal No. 96 of 2022) [2023] TZCA 17791](https://tanzlii.org/akn/tz/judgment/tzca/2023/17791) | Court of Appeal | Civil | on time | 62% |
| [Mohamed Abdillah Nur & Others v Hamad Masauni & Others (Civil Appeal No. 630 of 2023) [2024] TZCA 129](https://tanzlii.org/akn/tz/judgment/tzca/2024/129) | Court of Appeal | Civil | on time | 61% |
| [Tabu s/o Malebeti @ Medard & Others v Republic (Criminal Appeal No. 115 of 2020) [2023] TZCA 17945](https://tanzlii.org/akn/tz/judgment/tzca/2023/17945) | Court of Appeal | Criminal | overran | 58% |
| [Abdallah Juma Kambale v Noradi Tiliko Mongelwa (Civil Appeal No. 231 of 2018) [2023] TZCA 17730](https://tanzlii.org/akn/tz/judgment/tzca/2023/17730) | Court of Appeal | Civil | overran | 56% |
| [Sixbert Bayi Sanka v Rose Nehemia Samzugi (Civil Appeal No. 68 of 2022)](https://tanzlii.org/akn/tz/judgment/tzca/2023/227) | Court of Appeal | Civil | on time | 56% |
| [Oliva Damas Vegulla & Another v Mohamed Bashiri Telangwa (Civil Appeal No. 159 of 2019) [2022] TZCA 817](https://tanzlii.org/akn/tz/judgment/tzca/2022/817) | Court of Appeal | Civil | overran | 54% |
| [Fatuma Said Mahanyu v Republic (Criminal Appeal No. 323 of 2019) [2022] TZCA 628](https://tanzlii.org/akn/tz/judgment/tzca/2022/628) | Court of Appeal | Criminal | overran | 46% |
| [C.6533 D/Ssgt Hamis Ibrahim v Republic (Criminal Appeal No. 560 of 2019) [2022] TZCA 705](https://tanzlii.org/akn/tz/judgment/tzca/2022/705) | Court of Appeal | Criminal | overran | 46% |
| [Sadick Japhary @ Masunzu v Republic (Criminal Appeal No. 44 of 2019) [2022] TZCA 675](https://tanzlii.org/akn/tz/judgment/tzca/2022/675) | Court of Appeal | Criminal | overran | 46% |
| [Zengo Benjamin v Republic (Criminal Appeal No. 562 of 2019) [2022] TZCA 660](https://tanzlii.org/akn/tz/judgment/tzca/2022/660) | Court of Appeal | Criminal | overran | 46% |
| [Mroni Mtwena v Republic (Criminal Appeal No. 116 of 2019) [2022] TZCA 764](https://tanzlii.org/akn/tz/judgment/tzca/2022/764) | Court of Appeal | Criminal | overran | 46% |
| [Hassan Hussein v Republic (Criminal Appeal No. 41 of 2022) [2023] TZCA 17304](https://tanzlii.org/akn/tz/judgment/tzca/2023/17304) | Court of Appeal | Criminal | on time | 46% |
| [Jacob Mwashitete & Others v DPP (Criminal Appeal No. 24 of 2019) [2022] TZCA 69](https://tanzlii.org/akn/tz/judgment/tzca/2022/69) | Court of Appeal | Criminal | overran | 40% |
| [Oscar s/o Christopher & Others v Republic (Criminal Appeal No. 172 of 2022) [2023] TZCA 17336](https://tanzlii.org/akn/tz/judgment/tzca/2023/17336) | Court of Appeal | Criminal | on time | 40% |
| [Bahame Sitta & Another v Republic (Criminal Appeal No. 166 of 2019) [2022] TZCA 706](https://tanzlii.org/akn/tz/judgment/tzca/2022/706) | Court of Appeal | Criminal | overran | 36% |
| [Republic v John Mwaseba Mwasikili (Economic Case No. 3841 of 2024) [2024] TZHCCED 14](https://tanzlii.org/akn/tz/judgment/tzhcced/2024/14) | High Court | Economic | on time | 5% |
| [Republic v Antony Lazaro Ayo (Economic Case No. 2 of 2023) [2023] TZHCCED 20](https://tanzlii.org/akn/tz/judgment/tzhcced/2023/20) | High Court | Economic | on time | 5% |
| [Republic v Seuri Kisambu @ Mollel (Economic Case No. 6 of 2022) [2023] TZHCCED 19](https://tanzlii.org/akn/tz/judgment/tzhcced/2023/19) | High Court | Economic | on time | 5% |
| [Republic v Nicolaus Mlakoni Kimaro & Another (Economic Case No. 14 of 2021) [2021] TZHCCED 6684](https://tanzlii.org/akn/tz/judgment/tzhcced/2021/6684) | High Court | Economic | on time | 3% |
| [Republic v Mohabe Chacha Muriani (Criminal Session Case No. 56 of 2023) [2024] TZHC 859](https://tanzlii.org/akn/tz/judgment/tzhc/2024/859) | High Court | Criminal | on time | 1% |
| [Daniel Leornard Sanga @ Msauzi v Republic (Criminal Appeal No. 9801 of 2024) [2024] TZHC 5643](https://tanzlii.org/akn/tz/judgment/tzhc/2024/5643) | High Court | Criminal | on time | 1% |
| [Republic v Robert Simon Kisena & 3 Others (Economic Case No. 10 of 2022) [2023] TZHCCED 22](https://tanzlii.org/akn/tz/judgment/tzhcced/2023/22) | High Court | Economic | on time | 1% |
| [Republic v Halfan Hassan Bwire & 3 Others (Economic Case No. 16 of 2021) [2021] TZHCCED 6680](https://tanzlii.org/akn/tz/judgment/tzhcced/2021/6680) | High Court | Economic | on time | 1% |
| [Republic v Abdallah Khalifa & Another (Criminal Session Case No. 51 of 2023) [2024] TZHC 533](https://tanzlii.org/akn/tz/judgment/tzhc/2024/533) | High Court | Criminal | on time | 1% |
| [Republic v Juma Hamis (Criminal Session No. 15 of 2023) [2024] TZHC 5799](https://tanzlii.org/akn/tz/judgment/tzhc/2024/5799) | High Court | Criminal | on time | 1% |
| [Republic v Pascal Juma Swenya & Another (Criminal Sessions Case No. 53 of 2021) [2024] TZHC 1351](https://tanzlii.org/akn/tz/judgment/tzhc/2024/1351) | High Court | Criminal | overran | 1% |
| [Clemence Raphael v Republic (Criminal Appeal No. 148 of 2023) [2023] TZHC 22781](https://tanzlii.org/akn/tz/judgment/tzhc/2023/22781) | High Court | Criminal | on time | 1% |
| [Emmanuel Ngoila v Republic (Criminal Appeal No. 12 of 2023) [2023] TZHC 17823](https://tanzlii.org/akn/tz/judgment/tzhc/2023/17823) | High Court | Criminal | on time | 1% |
| [Mohamed Hassan & 5 Others v Republic (Criminal Appeal No. 12 of 2023) [2023] TZHC 19939](https://tanzlii.org/akn/tz/judgment/tzhc/2023/19939) | High Court | Criminal | on time | 0% |
| [Lanta Awi & 3 Others v Shammah Ministry Network & 4 Others (Land Case No. 38 of 2021) [2024] TZHC 1747](https://tanzlii.org/akn/tz/judgment/tzhc/2024/1747) | High Court | Land | overran | 0% |
| [Mikidadi Sarai Bakari v Rajabu Kassimu & 8 Others (Land Case No. 5 of 2021) [2024] TZHC 6093](https://tanzlii.org/akn/tz/judgment/tzhc/2024/6093) | High Court | Land | overran | 0% |
| [Mohamed Rashid Abdallah & 2 Others v Fahim Nizar Mukhi & 3 Others (Land Case No. 07 of 2021) [2024] TZHC 5471](https://tanzlii.org/akn/tz/judgment/tzhc/2024/5471) | High Court | Land | overran | 0% |
| [Anastasia Abel Nkini & 4 Others v Emmanuel Vehaeli Nkini (Land Case No. 1372 of 2024) [2024] TZHC 6220](https://tanzlii.org/akn/tz/judgment/tzhc/2024/6220) | High Court | Land | on time | 0% |
| [Athumani Bakari Kimbwigiri v Laurent Martine Lowri & 8 Others (Land Case No. 7 of 2020) [2023] TZHC 21217](https://tanzlii.org/akn/tz/judgment/tzhc/2023/21217) | High Court | Land | overran | 0% |
| [Janeth Josephat Ngung'u v Simon Abel Mbatian & 3 Others (Land Appeal No. 378 of 2023) [2023] TZHCLandD 17195](https://tanzlii.org/akn/tz/judgment/tzhclandd/2023/17195) | High Court | Land | on time | 0% |
| [Hidaya Shukuru v Joyce Joseph & 5 Others (Land Appeal No. 45 of 2023) [2023] TZHCLandD 16405](https://tanzlii.org/akn/tz/judgment/tzhclandd/2023/16405) | High Court | Land | on time | 0% |
| [Abdulrahman Malick Mugala v Tina Kassim Mohamed (Civil Appeal No. 143 of 2023) [2024] TZHC 211](https://tanzlii.org/akn/tz/judgment/tzhc/2024/211) | High Court | Civil | on time | 0% |
| [Lilian J. Mwambeleko v Joshua R. Gwakisa (Civil Appeal No. 48 of 2023) [2024] TZHC 942](https://tanzlii.org/akn/tz/judgment/tzhc/2024/942) | High Court | Civil | on time | 0% |
| [Hadija Hemedi Mchawindugu v Hamisi Ramadhani (Civil Appeal No. 178 of 2023) [2024] TZHC 1514](https://tanzlii.org/akn/tz/judgment/tzhc/2024/1514) | High Court | Civil | on time | 0% |
| [Ignas Benedict Diu v Aza Ally Rashid (Civil Appeal No. 39 of 2023)](https://tanzlii.org/akn/tz/judgment/tzhc/2023/23391) | High Court | Civil | on time | 0% |
| [Edes John Mlingi v Attorney General & Others (Land Case No. 1 of 2020) [2023] TZHC 20775](https://tanzlii.org/akn/tz/judgment/tzhc/2023/20775) | High Court | Land | overran | 0% |
| [Twaha Said Masawe v Salum Juma Ngonyani & 2 Others (Land Appeal No. 220 of 2023) [2023] TZHCLandD 17202](https://tanzlii.org/akn/tz/judgment/tzhclandd/2023/17202) | High Court | Land | on time | 0% |
| [Lilian Ogwali v Gerald Mwacha & 2 Others (Land Appeal No. 320 of 2023) [2024] TZHCLandD 203](https://tanzlii.org/akn/tz/judgment/tzhclandd/2024/203) | High Court | Land | on time | 0% |
| [Tanin Global Ltd v Athanasio Masenha & Another (Commercial Case No. 60 of 2023)](https://tanzlii.org/akn/tz/judgment/tzhccomd/2023/266) | High Court | Commercial | on time | 0% |
| [Amini Hassan Liutike v John Allen (Land Appeal No. 271 of 2023) [2023] TZHCLandD 17037](https://tanzlii.org/akn/tz/judgment/tzhclandd/2023/17037) | High Court | Land | on time | 0% |
| [Ali Yousufali Aladin v Munawer Dhiran & Another (Civil Case No. 9 of 2019) [2023] TZHC 16600](https://tanzlii.org/akn/tz/judgment/tzhc/2023/16600) | High Court | Civil | overran | 0% |
| [Tanpack Tissues Ltd v Alfred Mbussa (Labour Revision Application No. 648 of 2024) [2024] TZHCLD 44](https://tanzlii.org/akn/tz/judgment/tzhcld/2024/44) | High Court | Labour | on time | 0% |
| [Dellah Mlay v Mg Home & Estate Co Ltd (Revision Application No. 1430 of 2024) [2024] TZHCLD 49](https://tanzlii.org/akn/tz/judgment/tzhcld/2024/49) | High Court | Labour | on time | 0% |
| [Omary Hassani Tambali v Asha Halfa Ngoso & Another (Land Appeal No. 289 of 2023) [2023] TZHCLandD 17016](https://tanzlii.org/akn/tz/judgment/tzhclandd/2023/17016) | High Court | Land | on time | 0% |
| [Saidi Hussein & Another v Imani Kiriani (Land Appeal No. 306 of 2023) [2023] TZHCLandD 17236](https://tanzlii.org/akn/tz/judgment/tzhclandd/2023/17236) | High Court | Land | on time | 0% |
| [Bahati Juma Kimwana & Another v Registered Trustees of Islamic Propagation Center (Labour Revision No. 5 of 2023) [2024] TZHC 267](https://tanzlii.org/akn/tz/judgment/tzhc/2024/267) | High Court | Labour | on time | 0% |
| [Nelly Adolph Munuo v Prigeth Selestin Mokunda (Probate and Administration Cause No. 2231 of 2024) [2024] TZHC 1329](https://tanzlii.org/akn/tz/judgment/tzhc/2024/1329) | High Court | Probate | on time | 0% |
| [Abraham Nsubis Mwangakala v Andrew Abraham Mwangakala (Probate Cause No. 544 of 2024) [2024] TZHC 1652](https://tanzlii.org/akn/tz/judgment/tzhc/2024/1652) | High Court | Probate | on time | 0% |
| [Noreen Lionel Mawalla v Steve Lionel Mawalla (Probate Cause No. 59 of 2020) [2024] TZHC 851](https://tanzlii.org/akn/tz/judgment/tzhc/2024/851) | High Court | Probate | overran | 0% |
| [Jimmy John Mkenda v Manfred Clement Muya & Vera Mkenda (Probate Cause No. 66 of 2021) [2024] TZHC 1691](https://tanzlii.org/akn/tz/judgment/tzhc/2024/1691) | High Court | Probate | overran | 0% |
