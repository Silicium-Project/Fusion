#pragma once

#include <algorithm>
#include <cstddef>
#include <initializer_list>
#include <stdexcept>
#include <utility>
#include <vector>

namespace splitter {

// Map à base de vector trié (clé unique). Accès O(log n), mémoire compacte.
template <typename K, typename V>
class FlatMap {
public:
    using value_type = std::pair<K, V>;
    using container_type = std::vector<value_type>;
    using iterator = typename container_type::iterator;
    using const_iterator = typename container_type::const_iterator;

    FlatMap() = default;
    FlatMap(std::initializer_list<value_type> init) { insert(init.begin(), init.end()); }

    FlatMap& operator=(std::initializer_list<value_type> init) {
        data_.clear();
        insert(init.begin(), init.end());
        return *this;
    }

    bool insert(const K& key, const V& value) { return insert_impl(key, value); }
    bool insert(K&& key, V&& value) { return insert_impl(std::move(key), std::move(value)); }

    template <typename InputIt>
    void insert(InputIt first, InputIt last) {
        for (; first != last; ++first)
            insert(first->first, first->second);
    }

    iterator find(const K& key) {
        auto it = lower_bound(key);
        if (it != data_.end() && it->first == key)
            return it;
        return data_.end();
    }
    const_iterator find(const K& key) const {
        auto it = lower_bound(key);
        if (it != data_.end() && it->first == key)
            return it;
        return data_.end();
    }

    bool contains(const K& key) const { return find(key) != data_.end(); }

    V& operator[](const K& key) {
        auto it = lower_bound(key);
        if (it == data_.end() || it->first != key)
            it = data_.insert(it, {key, V{}});
        return it->second;
    }

    const V& at(const K& key) const {
        auto it = find(key);
        if (it == data_.end())
            throw std::out_of_range("FlatMap::at");
        return it->second;
    }

    iterator begin() noexcept { return data_.begin(); }
    const_iterator begin() const noexcept { return data_.begin(); }
    iterator end() noexcept { return data_.end(); }
    const_iterator end() const noexcept { return data_.end(); }

    std::size_t size() const noexcept { return data_.size(); }
    bool empty() const noexcept { return data_.empty(); }

    const container_type& values() const noexcept { return data_; }
    void clear() noexcept { data_.clear(); }

private:
    iterator lower_bound(const K& key) {
        return std::lower_bound(data_.begin(), data_.end(), key,
                                [](const value_type& kv, const K& k) { return kv.first < k; });
    }
    const_iterator lower_bound(const K& key) const {
        return std::lower_bound(data_.begin(), data_.end(), key,
                                [](const value_type& kv, const K& k) { return kv.first < k; });
    }

    template <typename KeyT, typename ValueT>
    bool insert_impl(KeyT&& key, ValueT&& value) {
        auto it = lower_bound(key);
        if (it != data_.end() && it->first == key)
            return false;
        data_.insert(it, {std::forward<KeyT>(key), std::forward<ValueT>(value)});
        return true;
    }

    container_type data_;
};

using FlatStringMap = FlatMap<std::string, std::string>;

}  // namespace splitter
