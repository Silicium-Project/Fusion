#pragma once

#include <algorithm>
#include <cstddef>
#include <initializer_list>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

namespace splitter {

template <typename T>
class FlatSet {
public:
    using container_type = std::vector<T>;
    using value_type = T;
    using iterator = typename container_type::iterator;
    using const_iterator = typename container_type::const_iterator;

    FlatSet() = default;
    FlatSet(std::initializer_list<T> init);

    FlatSet& operator=(std::initializer_list<T> init);

    bool insert(const T& value);
    bool insert(T&& value);
    bool insert(std::string_view value);

    iterator insert(const_iterator /*hint*/, const T& value);
    iterator insert(const_iterator /*hint*/, T&& value);

    iterator insert(iterator /*hint*/, const T& value);
    iterator insert(iterator /*hint*/, T&& value);

    template <typename InputIt>
    void insert(InputIt first, InputIt last);

    template <typename U>
    bool contains(const U& value) const;

    [[nodiscard]] iterator begin() noexcept;
    [[nodiscard]] const_iterator begin() const noexcept;
    [[nodiscard]] iterator end() noexcept;
    [[nodiscard]] const_iterator end() const noexcept;
    [[nodiscard]] bool empty() const noexcept;
    [[nodiscard]] std::size_t size() const noexcept;

    void clear() noexcept;

    const container_type& values() const noexcept;

    void merge(const FlatSet& other);

private:
    iterator insert_with_hint(const T& value);
    iterator insert_with_hint(T&& value);

    container_type values_;
};

using FlatStringSet = FlatSet<std::string>;

}  // namespace splitter

#include "support/FlatSet.tpp"
