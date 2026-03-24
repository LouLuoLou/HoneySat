#!/usr/bin/bash

PACKAGE_NAME="rccn_usr_ws"
PLATFORM="$1"
BRANCH="$2"

REF="$PACKAGE_NAME/$PLATFORM/$BRANCH"

# Create the desired filesystem structure
rm -rf ostree_root
mkdir -p ./ostree_root/usr/lib/$PACKAGE_NAME/
cp -r ./install/target ./ostree_root/usr/lib/$PACKAGE_NAME/

# Create the ostree repo if it does not exist
if [ ! -f ./repo/config ]; then
    ostree init \
        --repo=repo \
        --mode=archive
fi

# Add the build output files
ostree commit \
    --repo=repo \
    --branch="$REF" \
    --tree=dir=./ostree_root

# Push to server
ostree-push \
    --repo repo \
    deploy@deploy.rccn.space:repos/raccoon-mission \
    -p 2233 \
    "$REF"
