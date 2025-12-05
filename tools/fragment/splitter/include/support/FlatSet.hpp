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
    FlatSet(std::initializer_list<T> init) { insert(init.begin(), init.end()); }

    FlatSet& operator=(std::initializer_list<T> init) {
        values_.clear();
        insert(init.begin(), init.end());
        return *this;
    }

    bool insert(const T& value) {
        auto size_before = values_.size();
        insert_with_hint(value);
        return values_.size() != size_before;
    }
    bool insert(T&& value) {
        auto size_before = values_.size();
        insert_with_hint(std::move(value));
        return values_.size() != size_before;
    }

    bool insert(std::string_view value) {
        if constexpr (std::is_same_v<T, std::string>)
            return insert(std::string(value));
        else
            return insert(T(value));
    }

    iterator insert(const_iterator /*hint*/, const T& value) { return insert_with_hint(value); }
    iterator insert(const_iterator /*hint*/, T&& value) { return insert_with_hint(std::move(value)); }

    iterator insert(iterator /*hint*/, const T& value) { return insert_with_hint(value); }
    iterator insert(iterator /*hint*/, T&& value) { return insert_with_hint(std::move(value)); }

    template <typename InputIt>
    void insert(InputIt first, InputIt last) {
        for (; first != last; ++first)
            insert(*first);
    }

    template <typename U>
    bool contains(const U& value) const {
        return std::binary_search(values_.begin(), values_.end(), value);
    }

    [[nodiscard]] iterator begin() noexcept { return values_.begin(); }
    [[nodiscard]] const_iterator begin() const noexcept { return values_.begin(); }
    [[nodiscard]] iterator end() noexcept { return values_.end(); }
    [[nodiscard]] const_iterator end() const noexcept { return values_.end(); }
    [[nodiscard]] bool empty() const noexcept { return values_.empty(); }
    [[nodiscard]] std::size_t size() const noexcept { return values_.size(); }

    void clear() noexcept { values_.clear(); }

    const container_type& values() const noexcept { return values_; }

    void merge(const FlatSet& other) { insert(other.begin(), other.end()); }

private:
    iterator insert_with_hint(const T& value) {
        auto it = std::lower_bound(values_.begin(), values_.end(), value);
        if (it != values_.end() && *it == value)
            return it;
        return values_.insert(it, value);
    }

    iterator insert_with_hint(T&& value) {
        auto it = std::lower_bound(values_.begin(), values_.end(), value);
        if (it != values_.end() && *it == value)
            return it;
        return values_.insert(it, std::move(value));
    }

    container_type values_;
};

using FlatStringSet = FlatSet<std::string>;

}  // namespace splitter
