#!/usr/bin/env bash
# Clear the old stored default as well as the effective empty environment override.
set -euo pipefail
docker exec zeki-mongo mongosh --quiet zeki --eval 'const r=db.rocketchat_settings.updateOne({_id:"VoIP_TeamCollab_Ice_Servers",value:{$ne:""}},{$set:{value:""}}); print(JSON.stringify({setting:"VoIP_TeamCollab_Ice_Servers",modified:r.modifiedCount}));'
