#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2012 Bernard Blackham <bernard@largestprime.net>
# Copyright © 2010-2011 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2011 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2011 Matteo Boscariol <boscarim@hotmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

""" Utility to add multiple user to a contest.

    The input file is expected to be a single JSON file with two key "users" and "tags"
    This utility assume that the RankingServer is on the same machine.

    This differ with the default loader where it also integrate the "tags" which
    is used in the RankingServer
"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import argparse
import sys
import json

from cms import utf8_decoder
from cmsranking import Tag as RankingTag
from cmsranking import User as RankingUser
from cms.db import SessionGen, User, Contest, Participation, ask_for_contest

def main():
    """Parse arguments and launch process.

    """
    parser = argparse.ArgumentParser(
        description="Adds multiple user to a contest in CMS.")
    parser.add_argument("-c", "--contest-id", action="store", type=int,
                        help="id of contest where to add the user")
    parser.add_argument("input", type=argparse.FileType('r'), nargs=1,
                        help="input json file")
    args = parser.parse_args()

    if args.contest_id is None:
        args.contest_id = ask_for_contest()

    obj = json.load(args.input[0])

    for key in obj["users"]:
        if "first_name" not in obj["users"][key]:
            obj["users"][key]["first_name"] = obj["users"][key]["name"]
        if "last_name" not in obj["users"][key]:
            obj["users"][key]["last_name"] = ""
        obj["users"][key]["f_name"] = obj["users"][key]["first_name"]
        obj["users"][key]["l_name"] = obj["users"][key]["last_name"]
        if "team" not in obj["users"][key]:
            obj["users"][key]["team"] = None
        if "tags" not in obj["users"][key]:
            obj["users"][key]["tags"] = []

    with SessionGen() as session:
        contest = Contest.get_from_id(args.contest_id, session)

        for username in obj["users"]:
            userob = obj["users"][username]
            user = None
            if session.query(User).filter(User.username == username).count() > 0:
                print("Updating %s "%username)
                user = session.query(User).filter(User.username == username)[0]
                user.first_name = userob.get("first_name", user.first_name)
                user.last_name = userob.get("last_name", user.last_name)
                user.username = userob.get("username", user.username)
                user.password = userob.get("password", user.password)
                user.email = userob.get("email", user.email)
            else:
                print("Adding %s "%username)
                user = User(first_name=userob.get("first_name", ""),
                            last_name=userob.get("last_name", ""),
                            username=username,
                            password=userob.get("password", ""),
                            email=userob.get("email", ""))
                session.add(user)

            if session.query(Participation).filter(Participation.contest == contest).filter(Participation.user == user).count() == 0:
                print("Assigning %s to contest"%username)
                session.add(Participation(contest=contest, user=user, hidden=False, unrestricted=False))
            session.commit()

    print("Adding to ranking server")

    RankingTag.store.load_from_disk()
    RankingTag.store.merge_list(obj["tags"])
    RankingUser.store.load_from_disk()
    RankingUser.store.merge_list(obj["users"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
