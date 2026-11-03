# Builds the front-end footprint analyzer. The sha256 of the source is embedded at compile
# time (printed as analyzer_src_sha256 in every summary), so a summary can always be tied to
# the exact code that produced it even before the commit SHA (--analyzer-sha) exists.
#   make            -> ./lbr_footprint
#   make v1         -> also builds the V1 synthetic program in footprint_validate/
CXX      ?= g++
CXXFLAGS ?= -O2 -std=c++17 -Wall -Wextra
SRC      := lbr_footprint.cpp
SRC_SHA  := $(shell sha256sum $(SRC) | cut -c1-64)

lbr_footprint: $(SRC) Makefile
	$(CXX) $(CXXFLAGS) -DSRC_SHA256='"$(SRC_SHA)"' -o $@ $(SRC)

v1: lbr_footprint
	$(MAKE) -C footprint_validate

clean:
	rm -f lbr_footprint
	$(MAKE) -C footprint_validate clean

.PHONY: v1 clean
