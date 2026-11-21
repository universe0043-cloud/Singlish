# 第三方依赖、数据与素材声明

本清单说明目前核查到的来源，不替各权利人授予新的许可。自有项目代码尚未选择统一开源许可证，本轮不擅自增加项目级 LICENSE。课程提交不等于已获公开传播商业歌曲或设计素材的授权。

## Python 与模型

直接依赖的版本固定在 requirements.txt；完整验证环境已合并到同一份 requirements.txt；许可证元数据与许可文件映射见本说明下表。没有把虚拟环境、wheel、DLL 或模型权重打包入仓库。

| 组件 | 已检查的许可 |
| --- | --- |
| python-dotenv | BSD-3-Clause |
| OpenAI Python SDK | Apache-2.0 |
| faster-whisper | MIT |
| CTranslate2 | MIT |
| PyAV | BSD-3-Clause；二进制依赖 FFmpeg 另有自身许可，不能只按 PyAV 认定 |
| cmudict Python 包 | GPL-3.0-or-later；其 CMU 词典数据另附许可，两个均保留 |
| mutagen | GPL-2.0-or-later |
| NumPy | BSD-3-Clause，随发行版附其他组件声明 |
| httpx2 | 以安装包 LICENSE 和 dependencies.json 中元数据为准 |

转写权重为 [Systran/faster-whisper-small.en](https://huggingface.co/Systran/faster-whisper-small.en)，固定修订版见 README。权重来源于 [OpenAI Whisper](https://github.com/openai/whisper)，上游代码与权重为 MIT；模型转换工具仍有各自许可。本轮使用既有模型验证，未随 Git 再分发权重。

## 英式 IPA 词典

来源 [open-dict-data/ipa-dict](https://github.com/open-dict-data/ipa-dict)，其中英国英语数据源为 [leoboiko/ipacards](https://github.com/leoboiko/ipacards)，GPL-3.0。已保留数据原文、上游许可证、汇编许可证、URL 与内容哈希：`data/ipa_lexicon_source.json`、`data/EN_UK_LICENSE.txt`、`data/IPA_DICT_LICENSE.txt`。后续对该数据的修改也应保留来源和变更说明。

## 品牌视觉素材

`web/assets/singlish.svg` 与 `web/assets/headphone-note.svg` 内含从用户提供的最终确认图 `网页设计图1.png` 提取的图像（透明背景及指定蓝/棕色处理），不是普通字体或图标库资源。用户要求在首页与学习页共用。原设计作者、原始作品链接、使用许可尚未提供，需要作者补全；此处不声明为 MIT、CC0 或原创自由素材。设计图本身及本机绝对路径不入库。

## 课程研究材料

试标例句、参考草稿、模型输出与审计是本课程项目材料。歌曲录音不入库，研究记录中仍有歌词引用；需补充歌曲作者、录音版本、合法来源与课程引用依据。人工参考仍待复核。公开仓库前应由项目作者完成素材与数据权利核实；本次没有推送或公开。


## 最小提交版来源边界

代码和网页资源逐字节复制自当前原运行项目；仅新增离线评分工具和整理说明，不改分析规则。原实验、冻结参考、原响应和旧评分留在原项目归档中。最小版保留一份 40 题/55 参考/80 响应，不包含 56 条 AI 修订候选，也未以其评分。所有参考仍待人工终审。

原验证环境中 PyAV/FFmpeg、NumPy 等组件各自捆绑的声明继续保留。60 份许可文件中，逐字相同的副本合并；CMU 包的 GPL 原文与 data/EN_UK_LICENSE.txt 完全相同，指向同一份完整原文。其余 54 份不同的许可原文保存在 licenses/，不是省略许可内容。没有再分发依赖二进制或模型权重。

部分发行包安装记录没有提供许可原文，保留原元数据声明：flatbuffers（Apache 2.0）、tokenizers（Apache）、tqdm（MPL-2.0 与 MIT）。若以后再分发 wheel/二进制，需按实际发行包补齐 NOTICE 和捆绑组件声明。

### 验证环境依赖与许可映射

| 发行包 | 版本 | 原安装元数据许可 | 随附完整文本 |
| --- | --- | --- | --- |
| annotated-types | 0.8.0 | MIT | [01-LICENSE](licenses/annotated-types/01-LICENSE) |
| anyio | 4.16.0 | MIT | [01-LICENSE](licenses/anyio/01-LICENSE) |
| av | 16.1.0 | BSD-3-Clause | [01-LICENSE.txt](licenses/av/01-LICENSE.txt) |
| click | 8.5.1 | BSD-3-Clause | [01-LICENSE.txt](licenses/click/01-LICENSE.txt) |
| cmudict | 1.1.3 | GPL-3.0-or-later | [EN_UK_LICENSE.txt](data/EN_UK_LICENSE.txt), [01-LICENSE](licenses/cmudict/01-LICENSE) |
| colorama | 0.4.6 | License :: OSI Approved :: BSD License | [01-LICENSE.txt](licenses/colorama/01-LICENSE.txt) |
| ctranslate2 | 4.9.0 | MIT | [01-CTranslate2-LICENSE.txt](licenses/models/01-CTranslate2-LICENSE.txt) |
| faster-whisper | 1.2.1 | MIT | [01-LICENSE](licenses/faster-whisper/01-LICENSE) |
| filelock | 4.2.10 | MIT | [01-LICENSE](licenses/filelock/01-LICENSE) |
| flatbuffers | 25.12.19 | Apache 2.0 | 安装记录无随附原文；见上文 |
| fsspec | 2026.9.0 | BSD-3-Clause | [01-LICENSE](licenses/fsspec/01-LICENSE) |
| h11 | 0.16.0 | MIT | [01-LICENSE.txt](licenses/h11/01-LICENSE.txt) |
| hf-xet | 1.8.0 | Apache-2.0 | [01-LICENSE](licenses/hf-xet/01-LICENSE) |
| httpcore2 | 2.16.0 | BSD-3-Clause | [01-LICENSE.md](licenses/httpcore2/01-LICENSE.md) |
| httpx2 | 2.16.0 | BSD-3-Clause | [01-LICENSE.md](licenses/httpx2/01-LICENSE.md) |
| huggingface_hub | 2.4.0 | Apache-2.0 | [01-LICENSE](licenses/huggingface_hub/01-LICENSE) |
| idna | 3.20 | BSD-3-Clause | [01-LICENSE.md](licenses/idna/01-LICENSE.md) |
| importlib_metadata | 10.2.0 | Apache-2.0 | [01-LICENSE](licenses/importlib_metadata/01-LICENSE) |
| importlib_resources | 7.1.0 | Apache-2.0 | [01-LICENSE](licenses/importlib_metadata/01-LICENSE) |
| jiter | 0.19.0 | MIT | [01-LICENSE](licenses/jiter/01-LICENSE) |
| lazy-importer | 0.1.0 | Apache-2.0 | [01-LICENSE](licenses/lazy-importer/01-LICENSE) |
| mutagen | 1.47.0 | GPL-2.0-or-later | [01-COPYING](licenses/mutagen/01-COPYING) |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | [04-LICENSE.txt](licenses/numpy/04-LICENSE.txt), [01-LICENSE.txt](licenses/numpy/01-LICENSE.txt), [05-COPYING](licenses/numpy/05-COPYING), [06-LICENSE](licenses/numpy/06-LICENSE), [07-LICENSE.md](licenses/numpy/07-LICENSE.md), [08-LICENSE](licenses/numpy/08-LICENSE), [09-LICENSE.md](licenses/numpy/09-LICENSE.md), [10-LICENSE.txt](licenses/numpy/10-LICENSE.txt), [02-LICENSE](licenses/numpy/02-LICENSE), [03-LICENSE.md](licenses/numpy/03-LICENSE.md), [11-LICENSE.md](licenses/numpy/11-LICENSE.md), [12-LICENSE.md](licenses/numpy/12-LICENSE.md), [13-LICENSE.md](licenses/numpy/13-LICENSE.md), [14-LICENSE.md](licenses/numpy/14-LICENSE.md), [15-LICENSE.md](licenses/numpy/15-LICENSE.md), [16-LICENSE.md](licenses/numpy/16-LICENSE.md), [01-LICENSE.txt](licenses/numpy/01-LICENSE.txt), [02-LICENSE](licenses/numpy/02-LICENSE), [03-LICENSE.md](licenses/numpy/03-LICENSE.md) |
| onnxruntime | 1.32.0 | MIT License | [01-LICENSE](licenses/onnxruntime/01-LICENSE) |
| openai | 3.51.0 | Apache-2.0 | [02-LICENSE](licenses/openai/02-LICENSE), [01-LICENSE](licenses/openai/01-LICENSE) |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | [01-LICENSE](licenses/packaging/01-LICENSE), [02-LICENSE.APACHE](licenses/packaging/02-LICENSE.APACHE), [03-LICENSE.BSD](licenses/packaging/03-LICENSE.BSD) |
| protobuf | 7.36.2 | 3-Clause BSD License | [01-LICENSE](licenses/protobuf/01-LICENSE) |
| pydantic | 2.14.3 | MIT | [01-LICENSE](licenses/pydantic/01-LICENSE) |
| pydantic_core | 2.50.4 | MIT | [01-LICENSE](licenses/pydantic_core/01-LICENSE) |
| python-dotenv | 1.2.4 | BSD-3-Clause | [01-LICENSE](licenses/python-dotenv/01-LICENSE) |
| PyYAML | 6.0.3 | MIT | [01-LICENSE](licenses/PyYAML/01-LICENSE) |
| sniffio | 1.3.1 | MIT OR Apache-2.0 | [01-LICENSE](licenses/sniffio/01-LICENSE), [01-LICENSE](licenses/lazy-importer/01-LICENSE), [02-LICENSE.MIT](licenses/sniffio/02-LICENSE.MIT) |
| tokenizers | 0.23.3 | License :: OSI Approved :: Apache Software License | 安装记录无随附原文；见上文 |
| tqdm | 4.70.1 | MPL-2.0 AND MIT | 安装记录无随附原文；见上文 |
| truststore | 0.10.5 | MIT | [01-LICENSE](licenses/truststore/01-LICENSE) |
| typing-inspection | 0.4.5 | MIT | [01-LICENSE](licenses/typing-inspection/01-LICENSE) |
| typing_extensions | 4.16.0 | PSF-2.0 | [01-LICENSE](licenses/typing_extensions/01-LICENSE) |
| zipp | 4.1.2 | MIT | [01-LICENSE](licenses/zipp/01-LICENSE) |

### 原许可路径到保留文本的对应

以下为原归档路径到本目录的映射，重复项只合并文件，不改变原文。

| 原归档相对路径 | 本目录保留文本 |
| --- | --- |
| `licenses/CTranslate2-LICENSE.txt` | [licenses/models/01-CTranslate2-LICENSE.txt](licenses/models/01-CTranslate2-LICENSE.txt) |
| `licenses/python/annotated-types/annotated_types-0.8.0.dist-info/licenses/LICENSE` | [licenses/annotated-types/01-LICENSE](licenses/annotated-types/01-LICENSE) |
| `licenses/python/anyio/anyio-4.16.0.dist-info/licenses/LICENSE` | [licenses/anyio/01-LICENSE](licenses/anyio/01-LICENSE) |
| `licenses/python/av/av-16.1.0.dist-info/licenses/LICENSE.txt` | [licenses/av/01-LICENSE.txt](licenses/av/01-LICENSE.txt) |
| `licenses/python/click/click-8.5.1.dist-info/licenses/LICENSE.txt` | [licenses/click/01-LICENSE.txt](licenses/click/01-LICENSE.txt) |
| `licenses/python/cmudict/cmudict/data/LICENSE` | [licenses/cmudict/01-LICENSE](licenses/cmudict/01-LICENSE) |
| `licenses/python/cmudict/cmudict-1.1.3.dist-info/licenses/LICENSE` | [data/EN_UK_LICENSE.txt](data/EN_UK_LICENSE.txt) |
| `licenses/python/colorama/colorama-0.4.6.dist-info/licenses/LICENSE.txt` | [licenses/colorama/01-LICENSE.txt](licenses/colorama/01-LICENSE.txt) |
| `licenses/python/faster-whisper/faster_whisper-1.2.1.dist-info/LICENSE` | [licenses/faster-whisper/01-LICENSE](licenses/faster-whisper/01-LICENSE) |
| `licenses/python/filelock/filelock-4.2.10.dist-info/licenses/LICENSE` | [licenses/filelock/01-LICENSE](licenses/filelock/01-LICENSE) |
| `licenses/python/fsspec/fsspec-2026.9.0.dist-info/licenses/LICENSE` | [licenses/fsspec/01-LICENSE](licenses/fsspec/01-LICENSE) |
| `licenses/python/h11/h11-0.16.0.dist-info/licenses/LICENSE.txt` | [licenses/h11/01-LICENSE.txt](licenses/h11/01-LICENSE.txt) |
| `licenses/python/hf-xet/hf_xet-1.8.0.dist-info/licenses/LICENSE` | [licenses/hf-xet/01-LICENSE](licenses/hf-xet/01-LICENSE) |
| `licenses/python/httpcore2/httpcore2-2.16.0.dist-info/licenses/LICENSE.md` | [licenses/httpcore2/01-LICENSE.md](licenses/httpcore2/01-LICENSE.md) |
| `licenses/python/httpx2/httpx2-2.16.0.dist-info/licenses/LICENSE.md` | [licenses/httpx2/01-LICENSE.md](licenses/httpx2/01-LICENSE.md) |
| `licenses/python/huggingface_hub/huggingface_hub-2.4.0.dist-info/licenses/LICENSE` | [licenses/huggingface_hub/01-LICENSE](licenses/huggingface_hub/01-LICENSE) |
| `licenses/python/idna/idna-3.20.dist-info/licenses/LICENSE.md` | [licenses/idna/01-LICENSE.md](licenses/idna/01-LICENSE.md) |
| `licenses/python/importlib_metadata/importlib_metadata-10.2.0.dist-info/licenses/LICENSE` | [licenses/importlib_metadata/01-LICENSE](licenses/importlib_metadata/01-LICENSE) |
| `licenses/python/importlib_resources/importlib_resources-7.1.0.dist-info/licenses/LICENSE` | [licenses/importlib_metadata/01-LICENSE](licenses/importlib_metadata/01-LICENSE) |
| `licenses/python/jiter/jiter-0.19.0.dist-info/licenses/LICENSE` | [licenses/jiter/01-LICENSE](licenses/jiter/01-LICENSE) |
| `licenses/python/lazy-importer/lazy_importer-0.1.0.dist-info/licenses/LICENSE` | [licenses/lazy-importer/01-LICENSE](licenses/lazy-importer/01-LICENSE) |
| `licenses/python/mutagen/mutagen-1.47.0.dist-info/COPYING` | [licenses/mutagen/01-COPYING](licenses/mutagen/01-COPYING) |
| `licenses/python/numpy/numpy/_core/include/numpy/random/LICENSE.txt` | [licenses/numpy/01-LICENSE.txt](licenses/numpy/01-LICENSE.txt) |
| `licenses/python/numpy/numpy/ma/LICENSE` | [licenses/numpy/02-LICENSE](licenses/numpy/02-LICENSE) |
| `licenses/python/numpy/numpy/random/LICENSE.md` | [licenses/numpy/03-LICENSE.md](licenses/numpy/03-LICENSE.md) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/LICENSE.txt` | [licenses/numpy/04-LICENSE.txt](licenses/numpy/04-LICENSE.txt) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/numpy/_core/include/numpy/libdivide/LICENSE.txt` | [licenses/numpy/01-LICENSE.txt](licenses/numpy/01-LICENSE.txt) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/numpy/_core/src/common/pythoncapi-compat/COPYING` | [licenses/numpy/05-COPYING](licenses/numpy/05-COPYING) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/numpy/_core/src/highway/LICENSE` | [licenses/numpy/06-LICENSE](licenses/numpy/06-LICENSE) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/numpy/_core/src/npysort/x86-simd-sort/LICENSE.md` | [licenses/numpy/07-LICENSE.md](licenses/numpy/07-LICENSE.md) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/numpy/_core/src/umath/svml/LICENSE` | [licenses/numpy/08-LICENSE](licenses/numpy/08-LICENSE) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/numpy/fft/pocketfft/LICENSE.md` | [licenses/numpy/09-LICENSE.md](licenses/numpy/09-LICENSE.md) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/numpy/linalg/lapack_lite/LICENSE.txt` | [licenses/numpy/10-LICENSE.txt](licenses/numpy/10-LICENSE.txt) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/numpy/ma/LICENSE` | [licenses/numpy/02-LICENSE](licenses/numpy/02-LICENSE) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/numpy/random/LICENSE.md` | [licenses/numpy/03-LICENSE.md](licenses/numpy/03-LICENSE.md) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/numpy/random/src/distributions/LICENSE.md` | [licenses/numpy/11-LICENSE.md](licenses/numpy/11-LICENSE.md) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/numpy/random/src/mt19937/LICENSE.md` | [licenses/numpy/12-LICENSE.md](licenses/numpy/12-LICENSE.md) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/numpy/random/src/pcg64/LICENSE.md` | [licenses/numpy/13-LICENSE.md](licenses/numpy/13-LICENSE.md) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/numpy/random/src/philox/LICENSE.md` | [licenses/numpy/14-LICENSE.md](licenses/numpy/14-LICENSE.md) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/numpy/random/src/sfc64/LICENSE.md` | [licenses/numpy/15-LICENSE.md](licenses/numpy/15-LICENSE.md) |
| `licenses/python/numpy/numpy-2.5.4.dist-info/licenses/numpy/random/src/splitmix64/LICENSE.md` | [licenses/numpy/16-LICENSE.md](licenses/numpy/16-LICENSE.md) |
| `licenses/python/onnxruntime/onnxruntime/LICENSE` | [licenses/onnxruntime/01-LICENSE](licenses/onnxruntime/01-LICENSE) |
| `licenses/python/openai/openai/_vendor/httpx_aiohttp/LICENSE` | [licenses/openai/01-LICENSE](licenses/openai/01-LICENSE) |
| `licenses/python/openai/openai-3.51.0.dist-info/licenses/LICENSE` | [licenses/openai/02-LICENSE](licenses/openai/02-LICENSE) |
| `licenses/python/packaging/packaging-26.3.dist-info/licenses/LICENSE` | [licenses/packaging/01-LICENSE](licenses/packaging/01-LICENSE) |
| `licenses/python/packaging/packaging-26.3.dist-info/licenses/LICENSE.APACHE` | [licenses/packaging/02-LICENSE.APACHE](licenses/packaging/02-LICENSE.APACHE) |
| `licenses/python/packaging/packaging-26.3.dist-info/licenses/LICENSE.BSD` | [licenses/packaging/03-LICENSE.BSD](licenses/packaging/03-LICENSE.BSD) |
| `licenses/python/protobuf/protobuf-7.36.2.dist-info/LICENSE` | [licenses/protobuf/01-LICENSE](licenses/protobuf/01-LICENSE) |
| `licenses/python/pydantic/pydantic-2.14.3.dist-info/licenses/LICENSE` | [licenses/pydantic/01-LICENSE](licenses/pydantic/01-LICENSE) |
| `licenses/python/pydantic_core/pydantic_core-2.50.4.dist-info/licenses/LICENSE` | [licenses/pydantic_core/01-LICENSE](licenses/pydantic_core/01-LICENSE) |
| `licenses/python/python-dotenv/python_dotenv-1.2.4.dist-info/licenses/LICENSE` | [licenses/python-dotenv/01-LICENSE](licenses/python-dotenv/01-LICENSE) |
| `licenses/python/PyYAML/pyyaml-6.0.3.dist-info/licenses/LICENSE` | [licenses/PyYAML/01-LICENSE](licenses/PyYAML/01-LICENSE) |
| `licenses/python/sniffio/sniffio-1.3.1.dist-info/LICENSE` | [licenses/sniffio/01-LICENSE](licenses/sniffio/01-LICENSE) |
| `licenses/python/sniffio/sniffio-1.3.1.dist-info/LICENSE.APACHE2` | [licenses/lazy-importer/01-LICENSE](licenses/lazy-importer/01-LICENSE) |
| `licenses/python/sniffio/sniffio-1.3.1.dist-info/LICENSE.MIT` | [licenses/sniffio/02-LICENSE.MIT](licenses/sniffio/02-LICENSE.MIT) |
| `licenses/python/truststore/truststore-0.10.5.dist-info/licenses/LICENSE` | [licenses/truststore/01-LICENSE](licenses/truststore/01-LICENSE) |
| `licenses/python/typing-inspection/typing_inspection-0.4.5.dist-info/licenses/LICENSE` | [licenses/typing-inspection/01-LICENSE](licenses/typing-inspection/01-LICENSE) |
| `licenses/python/typing_extensions/typing_extensions-4.16.0.dist-info/licenses/LICENSE` | [licenses/typing_extensions/01-LICENSE](licenses/typing_extensions/01-LICENSE) |
| `licenses/python/zipp/zipp-4.1.2.dist-info/licenses/LICENSE` | [licenses/zipp/01-LICENSE](licenses/zipp/01-LICENSE) |
| `licenses/Whisper-LICENSE.txt` | [licenses/models/02-Whisper-LICENSE.txt](licenses/models/02-Whisper-LICENSE.txt) |
