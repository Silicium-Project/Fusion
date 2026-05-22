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
    FlatMap(std::initializer_list<value_type> init);

    FlatMap& operator=(std::initializer_list<value_type> init);

    bool insert(const K& key, const V& value);
    bool insert(K&& key, V&& value);

    template <typename InputIt>
    void insert(InputIt first, InputIt last);

    iterator find(const K& key);
    const_iterator find(const K& key) const;

    bool contains(const K& key) const;

    V& operator[](const K& key);

    const V& at(const K& key) const;

    iterator begin() noexcept;
    const_iterator begin() const noexcept;
    iterator end() noexcept;
    const_iterator end() const noexcept;

    std::size_t size() const noexcept;
    bool empty() const noexcept;

    const container_type& values() const noexcept;
    void clear() noexcept;

private:
    iterator lower_bound(const K& key);
    const_iterator lower_bound(const K& key) const;

    template <typename KeyT, typename ValueT>
    bool insert_impl(KeyT&& key, ValueT&& value);

    container_type data_;
};

using FlatStringMap = FlatMap<std::string, std::string>;

}  // namespace splitter

#include "support/FlatMap.tpp"
