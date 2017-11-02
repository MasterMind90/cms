#!/bin/bash

cmsInitDB

if [ "$(PGPASSWORD=password psql -h postgres -U cmsuser cmsdb -tAc "SELECT COUNT(*) FROM contests")" = '0' ]; then
    echo 'No contest detected. Importing from directory....'
    cmsImportContest -i -u -U /contest/
fi

if [ "$(PGPASSWORD=password psql -h postgres -U cmsuser cmsdb -tAc "SELECT COUNT(*) FROM admins WHERE username='$ADMIN_USERNAME'")" = '0' ]; then
    echo 'No admin detected. Adding One.'
    cmsAddAdmin -p $ADMIN_PASSWORD $ADMIN_USERNAME
fi

cmsResourceService -a 1
