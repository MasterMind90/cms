#!/usr/bin/env python3

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2013 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2016 Muhammad Amirul Ashraf <asdacap@gmail.com>
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

"""Utility to remove all users from a contest.

"""

import argparse
import sys

from cms import utf8_decoder
from cms.db import SessionGen, User, Participation, ask_for_contest


def remove_users(contest_id):
    """Remove all participations (and optionally users) from a contest.

    contest_id (int): the contest to remove users from.

    """
    with SessionGen() as session:
        # Remove all participations for this contest
        participations = session.query(Participation).filter(
            Participation.contest_id == contest_id).all()

        for participation in participations:
            session.delete(participation)

        session.commit()


def main():
    """Parse arguments and launch process.

    """
    parser = argparse.ArgumentParser(
        description="Remove all users from a CMS contest. "
        "This removes participations but keeps user accounts. "
        "Submissions are not deleted. May cause breakage.")
    parser.add_argument("-c", "--contest-id", action="store", type=int,
                        help="id of contest to remove users from")
    args = parser.parse_args()

    if args.contest_id is None:
        args.contest_id = ask_for_contest()

    remove_users(contest_id=args.contest_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())
