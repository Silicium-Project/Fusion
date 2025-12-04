#pragma once

#include <algorithm>
#include <cstddef>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace splitter {

class FlatStringSet {
public:
    using container_type = std::vector<std::string>;
    using value_type = std::string;
    using const_iterator = container_type::const_iterator;

    FlatStringSet() = default;

    bool insert(const std::string& value) { return insert_value(value); }
    bool insert(std::string&& value) { return insert_value(std::move(value)); }
    bool insert(std::string_view value) { return insert_value(std::string(value)); }

    template <typename InputIt>
    void insert(InputIt first, InputIt last) {
        for (; first != last; ++first)
            insert(*first);
    }

    [[nodiscard]] bool contains(std::string_view value) const {
        return std::binary_search(values_.begin(), values_.end(), value);
    }

    [[nodiscard]] const_iterator begin() const noexcept { return values_.begin(); }
    [[nodiscard]] const_iterator end() const noexcept { return values_.end(); }
    [[nodiscard]] bool empty() const noexcept { return values_.empty(); }
    [[nodiscard]] std::size_t size() const noexcept { return values_.size(); }

    void clear() noexcept { values_.clear(); }

    const container_type& values() const noexcept { return values_; }

    void merge(const FlatStringSet& other) { insert(other.begin(), other.end()); }

private:
    bool insert_value(const std::string& value) {
        auto it = std::lower_bound(values_.begin(), values_.end(), value);
        if (it != values_.end() && *it == value)
            return false;
        values_.insert(it, value);
        return true;
    }

    bool insert_value(std::string&& value) {
        auto it = std::lower_bound(values_.begin(), values_.end(), value);
        if (it != values_.end() && *it == value)
            return false;
        values_.insert(it, std::move(value));
        return true;
    }

    container_type values_;
};

}  // namespace splitter
