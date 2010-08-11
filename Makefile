CWD=$(shell pwd)
UP1=$(shell cd ..;pwd)
BUILD_DIR=${CWD}/build

NAME=pwrlogs

rpm: srpm
	rpmbuild --define "_specdir $(CWD)" --define "_sourcedir $(BUILD_DIR)" --define "_builddir $(BUILD_DIR)" --define "_srcrpmdir $(BUILD_DIR)" --define "_rpmdir $(BUILD_DIR)" --define "dist %nil" --nodeps -bb olpc-pwrlogs.spec

srpm: tarball
	rpmbuild --define "_specdir $(CWD)" --define "_sourcedir $(BUILD_DIR)" --define "_builddir $(BUILD_DIR)" --define "_srcrpmdir $(BUILD_DIR)" --define "_rpmdir $(BUILD_DIR)" --define "dist %nil" --nodeps -bs olpc-pwrlogs.spec

tarball:
	mkdir -p ${BUILD_DIR}
	tar cvzf ${BUILD_DIR}/${NAME}.tar.gz --exclude=~* olpc-pwr-log olpc-solar-log rtcwake-log rtcwake-screen-log process-pwr_log.py
	cp ${BUILD_DIR}/${NAME}.tar.gz ${BUILD_DIR}/${NAME}.tgz

key: tarball
	cpm ${BUILD_DIR}/${NAME}.t*gz
