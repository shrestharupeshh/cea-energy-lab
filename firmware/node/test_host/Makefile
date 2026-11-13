CXX ?= g++
CXXFLAGS = -std=c++17 -Wall -Wextra -Werror -O1
test: test_core
	./test_core
test_core: test_core.cpp ../lib/core/core.cpp ../lib/core/core.h
	$(CXX) $(CXXFLAGS) -o $@ test_core.cpp ../lib/core/core.cpp
clean:
	rm -f test_core
