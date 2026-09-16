# 根 Makefile 只负责装载模块；各流程说明见 makefiles/*/README.md。

include makefiles/common/Makefile.mk
include makefiles/ec2/Makefile.mk
include makefiles/local-dir/Makefile.mk
include makefiles/brand-ocr-yoloworld/Makefile.mk
include makefiles/brand-llm-ocr-yoloworld/Makefile.mk
include makefiles/brand-local-visual-llm/Makefile.mk
include makefiles/brand-yoloe-visual/Makefile.mk
include makefiles/diaper-category-ec2/Makefile.mk
include makefiles/brand-s3-ec2/Makefile.mk
